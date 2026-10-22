
from __future__ import annotations

import re
from typing import Any


def _tokens(text: str) -> list[str]:
    return re.findall(r"\b[a-z0-9]+\b", (text or "").lower())


def contains_rubric_overlap(response: str, rubric: str, phrase_length: int = 8) -> bool:
    """Return True when a distinctive sequence from the rubric is repeated."""
    response_words = _tokens(response)
    rubric_words = _tokens(rubric)
    if not response_words or not rubric_words or phrase_length < 1:
        return False
    if len(rubric_words) < phrase_length or len(response_words) < phrase_length:
        # Short expected answers still deserve protection; compare normalised
        # complete strings only when there is enough content to be meaningful.
        normal_response = " ".join(response_words)
        normal_rubric = " ".join(rubric_words)
        return len(normal_rubric) >= 4 and normal_rubric in normal_response
    rubric_phrases = {
        tuple(rubric_words[i:i + phrase_length])
        for i in range(len(rubric_words) - phrase_length + 1)
    }
    response_phrases = {
        tuple(response_words[i:i + phrase_length])
        for i in range(len(response_words) - phrase_length + 1)
    }
    return bool(rubric_phrases & response_phrases)


def _score_matches(response: str):
    """Return every line that matches the app's SCORE: <number|X> contract."""
    return list(re.finditer(
        r"^\s*SCORE\s*:\s*(X|-?\d+(?:\.\d+)?)\s*$",
        response or "",
        re.IGNORECASE | re.MULTILINE,
    ))


def check_output(
    response: str,
    rubric: str = "",
    *,
    attempt_number: int | None = None,
    rubric_provided: bool | None = None,
) -> dict[str, Any]:
    """Validate model output and return flags plus a recommended action.

    ``response`` is never silently rewritten here: callers must honour
    ``action`` and not display blocked output. No raw response/rubric is logged.
    """
    response = response if isinstance(response, str) else str(response or "")
    rubric = rubric if isinstance(rubric, str) else str(rubric or "")
    flags: list[str] = []

    try:
        from middleware.input_sanitizer import CANARY_TOKEN
    except (ImportError, AttributeError):
        CANARY_TOKEN = ""

    if CANARY_TOKEN and CANARY_TOKEN.lower() in response.lower():
        flags.append("canary_leak")

    leakage_patterns = (
        r"\bthe marking scheme is\b",
        r"\bthe expected answer is\b",
        r"\bthe model answer is\b",
        r"\bthe full rubric is\b",
        r"\bthe marking criteria are\b",
        r"\bmarks are awarded for\b",
        r"\bto receive full marks\b",
        r"\bhere is the (?:complete|full) solution\b",
        r"\bthe answer key is\b",
    )
    if any(re.search(pattern, response, re.IGNORECASE) for pattern in leakage_patterns):
        flags.append("possible_rubric_leak")

    if rubric_provided is False:
        flags.append("missing_rubric")
    elif rubric.strip() and contains_rubric_overlap(response, rubric):
        flags.append("possible_rubric_leak")

    # Student identifiers and contact details should not be echoed by feedback.
    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", response, re.I):
        flags.append("possible_pii_leak")
    if re.search(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", response):
        flags.append("possible_pii_leak")

    score_matches = _score_matches(response)
    score_match = score_matches[0] if len(score_matches) == 1 else None
    if not score_matches:
        flags.append("missing_or_invalid_score")
    elif len(score_matches) > 1:
        # Multiple score lines are ambiguous: quiz_agent.py parses the last one,
        # so validating only the first could let contradictory scores through.
        flags.append("multiple_score_lines")
    else:
        score_text = score_match.group(1).upper()
        if score_text != "X":
            score = float(score_text)
            if not 0.0 <= score <= 1.0:
                flags.append("score_out_of_range")

            feedback = re.sub(
                r"^\s*SCORE\s*:\s*(?:X|-?\d+(?:\.\d+)?)\s*$",
                "",
                response,
                flags=re.IGNORECASE | re.MULTILINE,
            ).strip().lower()
            says_correct = (
                "correct:" in feedback
                or "your answer is correct" in feedback
                or "great job!" in feedback
            )
            says_incorrect = (
                "incorrect:" in feedback
                or "your answer is not correct" in feedback
                or "your answer is wrong" in feedback
            )
            if (score == 1.0 and says_incorrect) or (
                score == 0.0 and says_correct and not says_incorrect
            ):
                flags.append("score_feedback_contradiction")

    # The attempt number is trusted application state, not model/user content.
    # It is included in results for auditability; rubric overlap blocks regardless
    # of attempt because the expected answer should never be echoed verbatim.
    flags = sorted(set(flags))
    blocking_flags = {
        "canary_leak", "possible_rubric_leak", "possible_pii_leak",
        "missing_rubric", "missing_or_invalid_score", "multiple_score_lines",
        "score_out_of_range", "score_feedback_contradiction",
    }
    action = "block" if blocking_flags.intersection(flags) else "allow"

    if flags:
        # Best-effort audit logging; never log student response or rubric text.
        try:
            from audit_logger import AuditLogger
            AuditLogger().log_event(
                event_type="output_guardrail_trigger",
                message="Student-facing model output was flagged by output guardrails.",
                severity="ERROR" if action == "block" else "WARNING",
                source_module="output_guardrails",
                metadata={
                    "flags": flags,
                    "action": action,
                    "attempt_number": attempt_number,
                },
            )
        except Exception:
            # Guardrail decisions must not depend on logging availability.
            pass

    return {
        "response": response,
        "flags": flags,
        "needs_review": bool(flags),
        "action": action,
        "score_match": score_match.group(1) if score_match else None,
        "attempt_number": attempt_number,
    }
