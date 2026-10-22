# Tests for the canary token check - does it catch a leak, does it leave
# a normal reply alone, and is the token actually still in the tutor prompt.

from __future__ import annotations

from pathlib import Path

from input_sanitizer import CANARY_TOKEN, contains_canary_leak

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_contains_canary_leak_true_when_token_present() -> None:
    response = f"Here is some internal context: {CANARY_TOKEN} that leaked."
    assert contains_canary_leak(response) is True


def test_contains_canary_leak_false_when_token_absent() -> None:
    response = "Correct! Your answer covers the key points of the rubric."
    assert contains_canary_leak(response) is False


def test_quiz_agent_tutor_instructions_contain_canary_token() -> None:
    # catches the token getting refactored out of the prompt by accident
    quiz_agent_path = PROJECT_ROOT / "1.4_agent2_quiz" / "quiz_agent.py"
    source = quiz_agent_path.read_text(encoding="utf-8")

    assert "CANARY_TOKEN" in source
    assert "Confidential internal reference marker" in source
