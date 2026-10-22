"""Tests for LLM daily cost-budget governance."""

import pytest

from rate_limiter import (
    DailyBudgetExceeded,
    GovernanceConfig,
    GovernedLLM,
    UsageGovernor,
)


class FakeResponse:
    """Simple response containing token usage metadata."""

    content = "Generated answer"

    usage_metadata = {
        "input_tokens": 1000,
        "output_tokens": 500,
    }


class FakeLLM:
    """Fake model used without making a real API request."""

    def __init__(self) -> None:
        self.call_count = 0

    def invoke(self, prompt: str) -> FakeResponse:
        self.call_count += 1
        return FakeResponse()


def test_governed_llm_records_token_cost() -> None:
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=10,
            window_seconds=60,
            daily_request_limit=20,
            daily_budget_usd=1.00,
        )
    )

    fake_llm = FakeLLM()

    governed_llm = GovernedLLM(
        fake_llm,
        caller_id="cost-test",
        governor=governor,
        provider="openai",
        input_cost_per_million_usd=1.00,
        output_cost_per_million_usd=1.00,
        max_output_tokens=100,
    )

    governed_llm.invoke("Test prompt")

    snapshot = governor.snapshot("cost-test")

    assert fake_llm.call_count == 1
    assert snapshot["daily_requests_used"] == 1
    assert snapshot["daily_cost_used_usd"] == pytest.approx(
        0.0015
    )


def test_request_blocked_before_exceeding_budget() -> None:
    governor = UsageGovernor(
        GovernanceConfig(
            enabled=True,
            requests=10,
            window_seconds=60,
            daily_request_limit=20,
            daily_budget_usd=0.0005,
        )
    )

    fake_llm = FakeLLM()

    governed_llm = GovernedLLM(
        fake_llm,
        caller_id="budget-test",
        governor=governor,
        provider="openai",
        input_cost_per_million_usd=1.00,
        output_cost_per_million_usd=1.00,
        max_output_tokens=1000,
    )

    with pytest.raises(DailyBudgetExceeded):
        governed_llm.invoke("Test prompt")

    assert fake_llm.call_count == 0