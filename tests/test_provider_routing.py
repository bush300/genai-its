"""Tests for configuration-driven LLM provider routing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


import llm_provider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "1.3_models"


def test_default_provider_is_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shared configuration should use Groq unless overridden."""

    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    assert (
        llm_provider.get_default_provider(llm_provider._LLM_CONFIG)
        == "groq"
    )


def test_optional_provider_modules_are_lazy_loaded() -> None:
    """Importing the router must not import optional provider adapters."""

    script = (
        "import sys;"
        f"sys.path.insert(0, {str(MODELS_DIR)!r});"
        "import llm_provider;"
        "print('ollama_llm' in sys.modules);"
        "print('openai_llm' in sys.modules)"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip().splitlines() == [
        "False",
        "False",
    ]


@pytest.mark.parametrize(
    ("provider", "override_name", "override_value"),
    [
        ("groq", "model", "test-groq-model"),
        ("ollama", "model_name", "test-ollama-model"),
        ("openai", "model", "test-openai-model"),
    ],
)
def test_provider_routing_accepts_model_aliases(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    override_name: str,
    override_value: str,
) -> None:
    """All routes should accept existing model/model_name call styles."""

    captured: dict[str, object] = {}
    sentinel = object()

    def fake_factory(**settings: object) -> object:
        captured.update(settings)
        return sentinel

    monkeypatch.setitem(
        llm_provider._PROVIDER_MAP,
        provider,
        fake_factory,
    )

    result = llm_provider.get_llm(
        provider=provider,
        apply_rate_limit=False,
        **{override_name: override_value},
    )

    assert result is sentinel
    assert captured[override_name] == override_value


def test_unknown_provider_is_rejected() -> None:
    """An unsupported provider should fail with a clear error."""

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        llm_provider.get_llm(
            provider="unsupported",
            apply_rate_limit=False,
        )
