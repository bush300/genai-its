# CyberNexa – Setup, Usage and Deployment Guide

CyberNexa is a secure, AI-powered Intelligent Tutoring System (ITS) for cybersecurity education.

The prototype uses Streamlit for the user interface, Firebase Firestore for persistent data, and configurable LLM providers including Groq, Ollama and OpenAI.

---

## 1. Prerequisites

Recommended local environment:

- Python 3.11 or 3.12
- Git
- Internet connection for cloud LLM providers
- Docker Desktop for container and Blue-Green deployment
- Ollama only when using a local LLM

> Python 3.11 or 3.12 is recommended for the current dependency set.

---

## 2. Clone the Repository

```bash
git clone https://github.com/bush300/genai-its.git
cd genai-its
```

Make sure the latest `main` branch is being used:

```bash
git switch main
git pull --ff-only origin main
```

---

## 3. Create a Virtual Environment

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

---

## 4. Install Dependencies

Upgrade pip and install the project requirements:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If a Gemini SDK dependency is missing, it can be installed separately with:

```bash
python -m pip install google-genai
```

If installation fails because of a temporary package-download or network error, retry the command after confirming internet access.

---

## 5. Configure Environment and Secrets

CyberNexa keeps private credentials outside the source code.

Create a local `.env` file using `.env.example` as a guide.

Example configuration:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
GOOGLE_API_KEY=your_gemini_key
```

The Google Gemini key is used by the security checking workflow.

If OpenAI is selected as the provider, configure the required OpenAI API key according to `.env.example`.

Also create:

```text
.streamlit/secrets.toml
```

using:

```text
.streamlit/secrets.example.toml
```

as a guide for Firebase and Streamlit secrets.

Do **not** commit real API keys, Firebase credentials, `.env`, or `secrets.toml` to GitHub.

---

## 5a. Create User Accounts

Students and Teachers log in with a username/password stored in the Firestore
`users` collection. There is no self-service sign-up; accounts are created
with:

```bash
python 1.5_security/create_account.py --username alice --role Student
python 1.5_security/create_account.py --username bob --role Teacher
```

You will be prompted for a password (hidden input, entered twice to confirm).
The script hashes it with bcrypt and writes `users/{username}` with
`password_hash` and `role`. It needs the same Firebase Admin credentials as
the main app, e.g.:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
```

Pass `--overwrite` to replace an existing account (e.g. to reset a password).

A student's account `username` is also their student ID: it is bound to the
login automatically and cannot be changed by the student, so one student
cannot view or edit another student's quiz progress.

---

## 6. Validate Configuration

Before starting the application, run:

```bash
python 1.5_security/config_validator.py
```

A valid configuration should return:

```text
[OK] Configuration validation passed.
```

---

## 7. Run Automated Tests

Run the official project test suite:

```bash
python -m pytest tests -q
```

The test suite covers application, security, provider, deployment and file-validation behaviour.

---

## 8. Run CyberNexa Locally

Start the Streamlit application with:

```bash
python -m streamlit run 1.1_interface/streamlit_app.py
```

Streamlit will display the local application URL in the terminal.

CyberNexa provides separate Student and Teacher portals.

---

## 9. LLM Provider Configuration

CyberNexa supports:

- **Groq** – cloud provider
- **Ollama** – local provider
- **OpenAI** – configurable cloud provider

The active provider is selected through the `LLM_PROVIDER` environment variable.

Example:

```env
LLM_PROVIDER=groq
```

To use Ollama locally:

```env
LLM_PROVIDER=ollama
```

Provider-specific model and governance configuration is maintained in:

```text
config/llm_config.yaml
```

The provider can therefore be changed without modifying the main application code.

---

## 10. Local Ollama Setup

Install Ollama separately, then download the required local model:

```bash
ollama pull llama3.2
```

Confirm that it is available:

```bash
ollama list
```

Then configure:

```env
LLM_PROVIDER=ollama
```

A provider smoke test can be run with:

```bash
python quick_test.py
```

---

## 11. Docker / Blue-Green Deployment

CyberNexa includes Blue-Green deployment infrastructure using Docker Compose and Nginx.

- **Blue** represents the current stable application version.
- **Green** represents the new candidate version.
- Nginx routes traffic to the active deployment slot.
- Health checks are used before switching traffic.
- Traffic can be rolled back to Blue if Green fails.

The Docker image also installs the Linux runtime libraries required by OpenCV and PDF-processing components.

### Local Docker secrets configuration

Private `.env` and Streamlit secret files are excluded from the Docker image and must not be committed.

For local end-to-end Docker testing, create:

```text
deploy/compose.local.yml
```

with:

```yaml
services:
  blue:
    env_file:
      - ../.env
    environment:
      LLM_PROVIDER: groq
    volumes:
      - ../.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro

  green:
    env_file:
      - ../.env
    environment:
      LLM_PROVIDER: groq
    volumes:
      - ../.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro
```

This local file should remain untracked because it references private local configuration.

### Start the Blue and Green services

For the standard deployment:

```bash
docker compose -f deploy/compose.blue-green.yml up --build -d
```

For local end-to-end testing with private configuration:

```bash
docker compose \
  -f deploy/compose.blue-green.yml \
  -f deploy/compose.local.yml \
  up --build -d
```

### Check service status

```bash
docker compose \
  -f deploy/compose.blue-green.yml \
  -f deploy/compose.local.yml \
  ps
```

Both `blue` and `green` should report a healthy status.

### Access the application

Open:

```text
http://localhost:8080
```

Nginx proxies requests to the currently active deployment slot.

### Check the active deployment slot

```bash
curl http://localhost:8080/deployment-slot
```

### Switch traffic to Green

From Bash, Git Bash, macOS Terminal or another Bash-compatible shell:

```bash
bash deploy/switch-slot.sh green
```

Verify:

```bash
curl http://localhost:8080/deployment-slot
```

Expected:

```text
green
```

### Roll back to Blue

```bash
bash deploy/switch-slot.sh blue
```

Verify:

```bash
curl http://localhost:8080/deployment-slot
```

Expected:

```text
blue
```

The HTTP response can also be checked with:

```bash
curl -I http://localhost:8080
```

The response should include:

```text
HTTP/1.1 200 OK
X-Deployment-Slot: blue
```

or the currently active deployment slot.

### View logs

```bash
docker compose \
  -f deploy/compose.blue-green.yml \
  -f deploy/compose.local.yml \
  logs --tail=100
```

### Stop the deployment

```bash
docker compose \
  -f deploy/compose.blue-green.yml \
  -f deploy/compose.local.yml \
  down
```

---

## 12. CI/CD

GitHub Actions provides automated quality and deployment checks.

The CyberNexa CI workflow includes:

- configuration validation
- Python syntax and compilation checks
- automated pytest execution
- automated coverage reporting
- generation of a `coverage.xml` coverage artifact
- checks preventing private credential files from being tracked

The Blue-Green Deployment Validation workflow checks:

- container build
- service startup
- health checks
- initial routing
- traffic switching
- rollback

---

## 13. Security and Governance

CyberNexa includes governance controls around LLM usage, including:

- request-rate limiting and daily request/cost budgets, tracked **per student**
  (each student's session is passed as a `caller_id`, so one student making
  heavy use of the tutor cannot exhaust another student's quota)
- input sanitisation: a navigation whitelist, a static keyword/regex filter,
  and a secondary Gemini LLM gate, in that order (see `1.5_security/README.md`
  and `1.5_security/input_sanitizer.py`). Oversized input is capped before it
  reaches the gate. The secondary gate **fails closed**: if every candidate
  Gemini model is unreachable, the input is treated as unsafe rather than let
  through.
- output guardrails, running after every tutor reply:
  - a canary-token check that detects the tutor leaking its own system
    instructions, logged to the audit log as `output_guardrail_trigger`
  - a rubric/answer-leak check (detecting the tutor's reply closely copying
    the stored marking rubric/answer) is planned but not yet implemented -
    `1.5_security/output_guardrail.py` is a placeholder pending that work
- a blocked-input banner that tells the student their input was blocked
  without repeating the detailed reason (the detail stays in the audit log,
  so a rejected prompt can't be used to learn how to refine the next attempt)
- an instructor release gate: a newly uploaded quiz is saved as a draft and
  is not shown to students until a teacher clicks **Approve** in the Teacher
  Hub; quizzes saved before this gate existed (with no `status` field) are
  still treated as published
- RBAC checks (`require_role`) on every Teacher/Student page, including the
  Security Events audit page
- the content-safety gate (`quiz_extractor._check_content_safe`) runs on
  every knowledge-base upload, PDF or plain text, before it's saved to
  Firestore
- `firestore.rules` denies all direct client access - every read/write goes
  through the Streamlit backend over the Firebase Admin SDK, never a
  browser/client SDK; see `docs/data_flow.md` for where data actually goes
- audit logging
- file-upload validation
- cloud egress masking

Before requests are sent to supported cloud LLM providers, sensitive values such as email addresses and student identifiers can be masked to reduce unnecessary exposure of personal information.

These controls help reduce misuse, unexpected API usage and exposure of restricted information.

---

## 14. Verification Status and Known Limitations

The Blue-Green deployment infrastructure has passed automated GitHub Actions validation for container build, service health, routing, traffic switching and rollback.

Manual end-to-end Docker testing has also verified the Student workflow through Nginx, including:

- application startup through `localhost:8080`
- Student portal access
- quiz loading
- Gemini-based security checking
- Groq-generated quiz feedback
- Blue-to-Green traffic switching
- Green-to-Blue rollback
- continued application operation after rollback

A local clean Docker rebuild previously encountered a temporary external Python package-download/build dependency error while installing the requirements. The failure occurred before the OpenCV runtime-library layer. The corresponding Dockerfile change has subsequently passed the repository's automated Blue-Green validation workflow.

Full end-to-end verification of every Teacher workflow and every external provider configuration is outside the scope of this installation check.

---

## 15. Quick Command Reference

```bash
# Validate configuration
python 1.5_security/config_validator.py

# Run tests
python -m pytest tests -q

# Start application locally
python -m streamlit run 1.1_interface/streamlit_app.py

# Test selected LLM provider
python quick_test.py

# Check local Ollama models
ollama list

# Start local Blue-Green deployment
docker compose \
  -f deploy/compose.blue-green.yml \
  -f deploy/compose.local.yml \
  up --build -d

# Check deployment containers
docker compose \
  -f deploy/compose.blue-green.yml \
  -f deploy/compose.local.yml \
  ps

# Check active slot
curl http://localhost:8080/deployment-slot

# Switch to Green
bash deploy/switch-slot.sh green

# Roll back to Blue
bash deploy/switch-slot.sh blue
```
