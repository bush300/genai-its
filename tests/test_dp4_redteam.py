# DP4 (institutional data sovereignty) red-team scenarios:
#   1. prompt injection trying to get a student's name/ID out to a cloud LLM
#   2. a knowledge-base upload carrying injected instructions
#   3. an unauthorised client trying to read/write Firestore directly

from __future__ import annotations

from pathlib import Path

from rate_limiter import _mask_sensitive_request

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --- Scenario 1: student identifiers must never reach a cloud provider ---

def test_student_id_is_redacted_before_it_would_leave_to_a_cloud_provider() -> None:
    request = "By the way, my student id: alice123, can you remember that?"
    masked = _mask_sensitive_request(request)

    assert "alice123" not in masked
    assert "[REDACTED_STUDENT_ID]" in masked


def test_email_is_redacted_before_it_would_leave_to_a_cloud_provider() -> None:
    request = "Contact me at alice@uni.edu.au if there's an issue with my mark."
    masked = _mask_sensitive_request(request)

    assert "alice@uni.edu.au" not in masked
    assert "[REDACTED_EMAIL]" in masked


def test_masking_also_applies_inside_nested_request_structures() -> None:
    request = [{"role": "user", "content": "student id: bob456"}]
    masked = _mask_sensitive_request(request)

    assert masked[0]["content"] == "student id: [REDACTED_STUDENT_ID]"


# --- Scenario 2: a KB upload with an injected instruction must be caught,
# regardless of whether it was uploaded as a .txt or a .pdf ---

def test_both_kb_upload_paths_run_the_content_safety_check() -> None:
    # regression guard: the .txt branch used to skip the safety check that
    # the .pdf branch already had, so a text KB upload could carry an
    # injection straight into Firestore unchecked
    app_source = (PROJECT_ROOT / "1.1_interface" / "streamlit_app.py").read_text(encoding="utf-8")

    text_branch = app_source.split('if kind == "text":', 1)[1].split('elif kind == "pdf":', 1)[0]
    pdf_branch = app_source.split('elif kind == "pdf":', 1)[1]

    assert "_check_content_safe" in text_branch
    assert "_pdf_to_text" in pdf_branch  # _pdf_to_text calls _check_content_safe internally


# --- Scenario 3: nothing should be able to read/write Firestore directly ---

def test_firestore_rules_deny_direct_client_access() -> None:
    rules = (PROJECT_ROOT / "firestore.rules").read_text(encoding="utf-8")

    assert "allow read, write: if false" in rules
