"""Automated tests for the shared LLM request governor."""

import asyncio
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECURITY_DIR = PROJECT_ROOT / "1.5_security"

if str(SECURITY_DIR) not in sys.path:
    sys.path.insert(0, str(SECURITY_DIR))


import rate_limiter  # noqa: E402

from rate_limiter import (  # noqa: E402
    DailyBudgetExceeded,
    GovernanceConfig,
    GovernedLLM,
    RateLimitExceeded,
    UsageGovernor,
)


class FakeLLM:
    """Fake model that does not contact a real LLM provider."""

    def invoke(self, message):
        return f"received: {message}"


def test_governed_llm_allows_requests_within_limit():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=2,
            window_seconds=60,
            daily_request_limit=10,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="allowed-user",
        governor=governor,
    )

    assert llm.invoke("one") == "received: one"
    assert llm.invoke("two") == "received: two"


def test_governed_llm_blocks_request_over_limit():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=2,
            window_seconds=60,
            daily_request_limit=10,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="blocked-user",
        governor=governor,
    )

    llm.invoke("one")
    llm.invoke("two")

    with pytest.raises(RateLimitExceeded):
        llm.invoke("three")


def test_disabled_governance_allows_all_requests():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=1,
            window_seconds=60,
            daily_request_limit=1,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="disabled-user",
        governor=governor,
    )

    assert llm.invoke("one") == "received: one"
    assert llm.invoke("two") == "received: two"


def test_request_window_limit_creates_audit_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=1,
            window_seconds=60,
            daily_request_limit=10,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="audit-window-user",
        governor=governor,
    )

    llm.invoke("first request")

    with pytest.raises(RateLimitExceeded):
        llm.invoke("blocked request")

    assert [
        event["event_type"]
        for event in events
    ] == [
        "llm_api_call",
        "rate_limit_hit",
    ]

    rate_limit_event = events[1]

    assert rate_limit_event["severity"] == "WARNING"
    assert (
        rate_limit_event["user_id"]
        == "audit-window-user"
    )
    assert (
        rate_limit_event["metadata"]["limit_type"]
        == "request_window"
    )


def test_daily_request_limit_creates_audit_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=10,
            window_seconds=60,
            daily_request_limit=1,
        )
    )

    governor.check_and_record(
        caller_id="audit-daily-user"
    )

    with pytest.raises(DailyBudgetExceeded):
        governor.check_and_record(
            caller_id="audit-daily-user"
        )

    assert len(events) == 1
    assert events[0]["event_type"] == "rate_limit_hit"
    assert events[0]["user_id"] == "audit-daily-user"
    assert (
        events[0]["metadata"]["limit_type"]
        == "daily_request"
    )


def test_daily_cost_limit_creates_audit_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=10,
            window_seconds=60,
            daily_request_limit=10,
            daily_budget_usd=0.50,
        )
    )

    with pytest.raises(DailyBudgetExceeded):
        governor.check_and_record(
            caller_id="audit-cost-user",
            estimated_cost_usd=0.75,
        )

    assert len(events) == 1
    assert events[0]["event_type"] == "rate_limit_hit"
    assert events[0]["user_id"] == "audit-cost-user"
    assert (
        events[0]["metadata"]["limit_type"]
        == "daily_cost"
    )


def test_successful_llm_call_creates_audit_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=1,
            window_seconds=60,
            daily_request_limit=1,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="successful-user",
        governor=governor,
        provider="groq",
    )

    result = llm.invoke("test request")

    assert result == "received: test request"
    assert len(events) == 1
    assert events[0]["event_type"] == "llm_api_call"
    assert events[0]["severity"] == "INFO"
    assert events[0]["user_id"] == "successful-user"
    assert events[0]["metadata"] == {
        "provider": "groq",
        "operation": "invoke",
        "successful": True,
    }


def test_failed_llm_call_creates_system_error_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    class FailingLLM:
        def invoke(self, message):
            raise RuntimeError("Provider unavailable")

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=1,
            window_seconds=60,
            daily_request_limit=1,
        )
    )

    llm = GovernedLLM(
        FailingLLM(),
        caller_id="failed-user",
        governor=governor,
        provider="openai",
    )

    with pytest.raises(
        RuntimeError,
        match="Provider unavailable",
    ):
        llm.invoke("test request")

    assert len(events) == 1
    assert events[0]["event_type"] == "system_error"
    assert events[0]["severity"] == "ERROR"
    assert events[0]["user_id"] == "failed-user"
    assert events[0]["metadata"] == {
        "provider": "openai",
        "operation": "invoke",
        "error_type": "RuntimeError",
    }


def test_successful_async_llm_call_creates_audit_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    class AsyncFakeLLM:
        async def ainvoke(self, message):
            return f"received: {message}"

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=1,
            window_seconds=60,
            daily_request_limit=1,
        )
    )

    llm = GovernedLLM(
        AsyncFakeLLM(),
        caller_id="async-user",
        governor=governor,
        provider="ollama",
    )

    result = asyncio.run(
        llm.ainvoke("async request")
    )

    assert result == "received: async request"
    assert len(events) == 1
    assert events[0]["event_type"] == "llm_api_call"
    assert events[0]["metadata"] == {
        "provider": "ollama",
        "operation": "ainvoke",
        "successful": True,
    }


def test_failed_async_llm_call_creates_system_error_event(
    monkeypatch,
):
    events = []

    monkeypatch.setattr(
        rate_limiter,
        "_audit_safely",
        lambda **event: events.append(event),
    )

    class FailingAsyncLLM:
        async def ainvoke(self, message):
            raise ConnectionError(
                "Async provider unavailable"
            )

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=1,
            window_seconds=60,
            daily_request_limit=1,
        )
    )

    llm = GovernedLLM(
        FailingAsyncLLM(),
        caller_id="failed-async-user",
        governor=governor,
        provider="groq",
    )

    with pytest.raises(
        ConnectionError,
        match="Async provider unavailable",
    ):
        asyncio.run(
            llm.ainvoke("async request")
        )

    assert len(events) == 1
    assert events[0]["event_type"] == "system_error"
    assert events[0]["metadata"] == {
        "provider": "groq",
        "operation": "ainvoke",
        "error_type": "ConnectionError",
    }


# ---------------------------------------------------------------------------
# FR14 - Egress controls and sensitive-data masking tests
# ---------------------------------------------------------------------------


def test_groq_masks_email_and_student_id():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=10,
            window_seconds=60,
            daily_request_limit=100,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="groq-mask-test",
        governor=governor,
        provider="groq",
    )

    result = llm.invoke(
        "Contact saad@example.com "
        "for student ID: saad_123"
    )

    assert (
        result
        == "received: Contact [REDACTED_EMAIL] "
        "for student ID: [REDACTED_STUDENT_ID]"
    )

    assert "saad@example.com" not in result
    assert "saad_123" not in result


def test_openai_masks_structured_message_content():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=10,
            window_seconds=60,
            daily_request_limit=100,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="openai-mask-test",
        governor=governor,
        provider="openai",
    )

    request = [
        {
            "role": "system",
            "content": (
                "Student email is test@example.com "
                "and student_id=abc_456"
            ),
        }
    ]

    result = llm.invoke(request)

    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_STUDENT_ID]" in result
    assert "test@example.com" not in result
    assert "abc_456" not in result


def test_ollama_keeps_sensitive_request_unchanged():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=10,
            window_seconds=60,
            daily_request_limit=100,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="ollama-mask-test",
        governor=governor,
        provider="ollama",
    )

    original = (
        "Contact saad@example.com "
        "for student ID: saad_123"
    )

    result = llm.invoke(original)

    assert result == f"received: {original}"
    assert "saad@example.com" in result
    assert "saad_123" in result


def test_cloud_provider_does_not_mask_normal_text():
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=10,
            window_seconds=60,
            daily_request_limit=100,
        )
    )

    llm = GovernedLLM(
        FakeLLM(),
        caller_id="normal-text-test",
        governor=governor,
        provider="groq",
    )

    original = (
        "Explain student performance for week2"
    )

    result = llm.invoke(original)

    assert result == f"received: {original}"


def test_async_cloud_request_masks_sensitive_data():
    class AsyncFakeLLM:
        async def ainvoke(self, message):
            return f"received: {message}"

    governor = UsageGovernor(
        GovernanceConfig(
            enabled=False,
            requests=10,
            window_seconds=60,
            daily_request_limit=100,
        )
    )

    llm = GovernedLLM(
        AsyncFakeLLM(),
        caller_id="async-mask-test",
        governor=governor,
        provider="groq",
    )

    result = asyncio.run(
        llm.ainvoke(
            "Email: async@example.com "
            "student number: async_789"
        )
    )

    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_STUDENT_ID]" in result
    assert "async@example.com" not in result
    assert "async_789" not in result