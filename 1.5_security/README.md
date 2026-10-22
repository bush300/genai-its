# Module 5: Audit & Observability

Owner: Sujal Kumar  
Project: CyberNexa / GenAI ITS  
Branch: sujal-audit-observability

## Purpose

This module provides audit logging and observability support for the CyberNexa GenAI Intelligent Tutoring System.

The audit logger records important system, security, and AI interaction events in a structured format. These logs can support incident response, compliance review, debugging, and future dashboard monitoring.

## Design Principles Supported

This module supports:

- DP3: Bounded Prompt Contracts
- DP4: Institutional Data Sovereignty
- DP8: Prompt Engineering as Pedagogy

Audit logging helps make system behaviour more transparent without exposing sensitive student data, prompts, answer keys, or credentials.

## Current Implementation

The current implementation is located in:

`1.5_security/audit_logger.py`

At this stage, the logger writes audit events locally to:

`logs/audit_logs.jsonl`

The `logs/` folder is excluded from Git using `.gitignore` because runtime audit logs may contain sensitive or temporary development data.

## Audit Event Structure

Each audit event follows this structure:

- `event_id`
- `timestamp`
- `event_type`
- `severity`
- `user_id`
- `session_id`
- `source_module`
- `message`
- `metadata`

This structure is designed to work locally during development and later map cleanly into Firestore.

## Supported Event Types

The logger currently supports:

- `auth_attempt`
- `rbac_check`
- `input_sanitisation_flag`
- `output_guardrail_trigger`
- `rate_limit_hit`
- `llm_api_call`
- `quiz_state_change`
- `prompt_template_change`
- `contract_violation`
- `system_error`

## Supported Severity Levels

The logger supports:

- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

## Privacy and Metadata Sanitisation

Audit logs should not expose sensitive student or system information. The logger automatically redacts sensitive metadata fields before writing them to log output.

The following fields are redacted if found in metadata:

- `password`
- `api_key`
- `secret`
- `token`
- `private_key`
- `raw_prompt`
- `full_prompt`
- `student_answer`
- `rubric`
- `answer_key`

If a sensitive field is found, its value is replaced with:

`[REDACTED]`

Long metadata values are also truncated to reduce accidental over-logging.

## Firestore Preparation

Firestore has been manually prepared in the CyberNexa Firebase project.

A collection has been created called:

`audit_logs`

A manual test document has also been added to confirm the intended structure. The Firestore document uses the same fields as the local audit logger:

- `event_id`
- `timestamp`
- `event_type`
- `severity`
- `user_id`
- `session_id`
- `source_module`
- `message`
- `metadata`

At this stage, Firestore integration is not yet hardcoded into the logger. This is intentional because the logger should continue working locally even if Firebase credentials are not available.

## Testing

Automated tests are located in:

`tests/test_audit_logger.py`

Run the tests with:

python3 -m pytest tests/test_audit_logger.py

## Sprint 3 Progress

The audit logger now supports optional Firestore storage using the `audit_logs` collection.

Each event is first written to the local JSONL audit file. The same sanitised event is then written to Firestore when the database connection is enabled. If Firestore is unavailable, the local audit record remains available as a fallback.

A controlled `contract_violation` event was successfully written to the live Firestore database. The event represented a prompt-injection attempt and included information such as the event type, severity, source module and guardrail result. The original prompt was replaced with `[REDACTED]` before storage.

### Testing Status

* 7 core audit logger tests passed.
* 5 mocked Firestore integration tests passed.
* 12 tests passed in total.
* Live Firestore writing was verified manually.
* Local fallback behaviour was tested.

### Red-Team Testing Preparation

A red-team testing plan has been prepared for the following scenarios:

* Prompt injection
* System-prompt extraction
* Answer-key extraction
* Rubric leakage
* Role bypass
* Rate-limit abuse
* Malicious file instructions
* Unsafe cybersecurity requests

Each scenario has been mapped to an expected system response, audit-event type, severity level and responsible module.

### Current Limitation

The controlled prompt-injection event demonstrates that the audit logging and Firestore storage pipeline works.

It does not yet represent a complete end-to-end attack passing through the real CyberNexa AI Gate. Full testing requires the AI Gate, rate limiter, file validator, output guardrails and access-control components to be combined into one shared integration branch.

### Next Step

Once a shared integration branch is confirmed, the red-team scenarios can be converted into automated Pytest cases that send controlled attacks into the real system and verify that they are blocked, sanitised and logged correctly.

## Runtime Audit Integration

The audit logger is connected to the real rate limiter and LLM wrapper.

It automatically records:

- `rate_limit_hit` when an enforced limit is exceeded
- `llm_api_call` after a successful model request
- `system_error` when an LLM provider request fails

Audit events contain operational metadata only. API keys, raw prompts, student answers, rubrics, answer keys and model response content are not logged.

Runtime events are stored locally in `logs/audit_logs.jsonl`.

To watch the audit log while using the application:

    tail -f logs/audit_logs.jsonl

Run the project tests with:

    python3 -m pytest tests -q

At the time of integration, all 35 tests passed.

## Later security/governance additions

The following were added alongside the audit logger described above, as part
of closing out the project's security coverage:

- **Per-student rate/budget limits.** `QuizAgent` now passes the student's ID
  through to `get_llm(..., caller_id=student_id)` (see `1.4_agent2_quiz/quiz_agent.py`),
  so each student has an independent request-window, daily-request and
  daily-cost counter in `rate_limiter.UsageGovernor`. Previously every student
  shared one `"global"` bucket, so one student's usage could block everyone
  else from using the tutor for the rest of the day.
- **Rate-limit/budget errors shown as friendly messages.** `RateLimitExceeded`
  and `DailyBudgetExceeded` (both raised from `rate_limiter.py`) are now caught
  around the call to `agent.handle_input(...)` in `streamlit_app.py` and shown
  with `st.warning(...)` instead of surfacing a raw traceback.
- **Canary hits are now audit-logged.** Detecting `CANARY_TOKEN` in a tutor
  reply writes an `output_guardrail_trigger` event (severity `CRITICAL`)
  before the student is shown the exfiltration-detected message. Previously
  this was only shown in the UI and never recorded.
- **Output guardrail (rubric/answer-leak detection) - pending.**
  `1.5_security/output_guardrail.py` exists as a placeholder; the comparison
  logic (tutor reply vs. stored rubric/answer, replace a close copy with a
  safe message, log `output_guardrail_trigger`) is Anthony's to land there so
  we don't build it twice. `streamlit_app.py` already captures the current
  question before calling the tutor model, ready for this to be wired in.
- **Input length cap.** `input_sanitizer.cap_input_length()` caps
  a student answer to `MAX_INPUT_CHARS` (4000) before it reaches the secondary
  gate, bounding gate cost/latency and blunting "bury the instruction in a
  wall of text" injection attempts.
- **Blocked-input banner is now generic.** The red banner shown when input is
  blocked no longer echoes the gate's detailed `reason` to the student; the
  detail is still written to the audit log (`input_sanitisation_flag` event).
- **RBAC gap fixed.** The Security Events page (`teacher_security`) was
  missing its `require_role("Teacher")` check and was reachable by any
  authenticated session; it now requires the Teacher role like every other
  teacher-only page.
- **Student ID bound to login.** `st.session_state.student_id` is now set
  directly from the authenticated username at login. The old `?student_id=`
  query-param override and the student-ID dropdown are removed, since both
  let one student view or act as another student by editing the URL or
  picking a different ID.
- **Account creation script.** `1.5_security/create_account.py` hashes a
  password with bcrypt and writes `users/{username}` with `password_hash` and
  `role`, so accounts are created through one consistent path instead of
  manual Firestore edits. See `README_CyberNexa.md` section "Create User
  Accounts".
- **Instructor release gate.** `1.2_back_end/quiz_publication.py` adds
  `is_quiz_published()` / `resolve_save_status()`. A newly uploaded quiz is
  saved with `status: "draft"`; a teacher approves it from the Teacher Hub,
  which sets `status: "published"`; the student-facing subject/week lists
  only include published quizzes (a missing `status` field is treated as
  published, so quizzes created before this gate existed keep working).
- **Text knowledge-base uploads now go through the content-safety gate too.**
  The PDF upload path already called `quiz_extractor._check_content_safe`
  before saving KB content to Firestore; the `.txt` path didn't, so a plain
  text file with injected instructions could skip the gate entirely and sit
  in Firestore feeding every future quiz evaluation for that subject/week.
  Both paths now call the same check.
- **`firestore.rules`** (repo root) denies all direct client reads/writes.
  Everything in this app goes through the Streamlit backend over the
  Firebase Admin SDK, which bypasses these rules anyway - this is a backstop
  in case a client key ever ends up somewhere it shouldn't. **Not deployed
  yet** - rules only take effect after `firebase deploy --only firestore:rules`
  (with a `firebase.json` pointing at this file), which hasn't been set up.
- **`docs/data_flow.md`** - a short diagram of what data goes where, and
  what's masked before it reaches a cloud LLM provider.
- **DP4 red-team tests** (`tests/test_dp4_redteam.py`) cover the three
  scenarios from the DP4 spec: student identifiers getting masked before
  reaching a cloud provider, a KB upload carrying injected content, and
  direct (non-Admin-SDK) Firestore access being denied by the rules file.

Tests for all of the above live in `tests/test_canary.py`,
`tests/test_input_sanitizer.py` (fail-closed gate, length cap),
`tests/test_quiz_publication.py`, `tests/test_create_account.py` and
`tests/test_dp4_redteam.py`.

### RT-06 Rate-Limit Abuse Test

The RT-06 demonstration sends repeated requests through the real rate limiter, confirms that the excessive request is blocked, creates a genuine `rate_limit_hit` event and verifies the event in the Firestore `audit_logs_test` collection.

Run it with:

    python3 1.5_security/rt06_rate_limit_firestore_demo.py

RT-06 is currently the completed end-to-end red-team scenario. Other scenarios require their relevant controls, including the AI Gate, output guardrails, access control and file validation.
