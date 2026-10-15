"""Offline tests for the CyberNexa security benchmark."""

from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = (
    PROJECT_ROOT
    / "1.5_security"
    / "security_benchmark.py"
)

spec = importlib.util.spec_from_file_location(
    "security_benchmark",
    BENCHMARK_PATH,
)

security_benchmark = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(security_benchmark)


class FakeSanitizer:
    """Deterministic replacement for InputSanitizer."""

    def __init__(self, is_safe: bool, reason: str):
        self.is_safe = is_safe
        self.reason = reason
        self.received_prompt = None

    def check_secondary_gate(self, prompt: str):
        self.received_prompt = prompt
        return self.is_safe, self.reason


def test_benchmark_case_sets_have_expected_sizes_and_unique_ids():
    attacks = security_benchmark.ATTACK_CASES
    normal = security_benchmark.NORMAL_CASES

    assert len(attacks) == 10
    assert len(normal) == 10

    all_ids = [
        case["id"]
        for case in attacks + normal
    ]

    assert len(all_ids) == len(set(all_ids))


def test_classify_result():
    assert (
        security_benchmark.classify_result(
            True,
            "OK",
        )
        == "allowed"
    )

    assert (
        security_benchmark.classify_result(
            False,
            "Blocked by static filter",
        )
        == "blocked"
    )

    assert (
        security_benchmark.classify_result(
            False,
            "Security check unavailable: timeout",
        )
        == "unavailable"
    )


def test_percentage():
    assert security_benchmark.percentage(10, 10) == 100.0
    assert security_benchmark.percentage(0, 10) == 0.0
    assert security_benchmark.percentage(1, 4) == 25.0
    assert security_benchmark.percentage(1, 0) == 0.0


def test_run_case_attack_blocked():
    sanitizer = FakeSanitizer(
        is_safe=False,
        reason="Blocked by static filter",
    )

    case = {
        "id": "TEST-A",
        "category": "prompt_injection",
        "prompt": "Synthetic attack prompt",
    }

    result = security_benchmark.run_case(
        sanitizer,
        case,
        expected="blocked",
    )

    assert result["case_id"] == "TEST-A"
    assert result["result"] == "blocked"
    assert result["passed"] is True
    assert result["latency_ms"] >= 0
    assert sanitizer.received_prompt == case["prompt"]


def test_run_case_normal_allowed():
    sanitizer = FakeSanitizer(
        is_safe=True,
        reason="OK",
    )

    case = {
        "id": "TEST-N",
        "category": "normal_answer",
        "prompt": "Synthetic legitimate answer",
    }

    result = security_benchmark.run_case(
        sanitizer,
        case,
        expected="allowed",
    )

    assert result["case_id"] == "TEST-N"
    assert result["result"] == "allowed"
    assert result["passed"] is True
    assert result["latency_ms"] >= 0


def test_run_case_unavailable_is_not_counted_as_pass():
    sanitizer = FakeSanitizer(
        is_safe=False,
        reason="Security check unavailable: timeout",
    )

    case = {
        "id": "TEST-U",
        "category": "disguised_injection",
        "prompt": "Synthetic unavailable case",
    }

    result = security_benchmark.run_case(
        sanitizer,
        case,
        expected="blocked",
    )

    assert result["result"] == "unavailable"
    assert result["passed"] is False
