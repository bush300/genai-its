"""Configuration-driven LLM provider factory.

Author: Saad

Supported providers:
- Ollama for local execution
- Groq for cloud execution
- OpenAI for cloud execution

Provider selection, pricing and default settings are loaded from:
config/llm_config.yaml
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECURITY_DIR = PROJECT_ROOT / "1.5_security"

if str(SECURITY_DIR) not in sys.path:
    sys.path.insert(0, str(SECURITY_DIR))

# Load local API keys before reading provider configuration.
load_dotenv(PROJECT_ROOT / ".env", override=False)

from llm_config import (  # noqa: E402
    apply_governance_environment,
    get_default_provider,
    get_provider_settings,
    load_llm_config,
)

# Apply YAML governance settings before the shared governor is created.
_LLM_CONFIG = load_llm_config()
apply_governance_environment(_LLM_CONFIG)

from rate_limiter import apply_governance  # noqa: E402


ProviderFactory = Callable[..., Any]


def _create_groq(**settings: Any) -> Any:
    """Load Groq only when that provider is selected."""

    try:
        from groq_llm import create_groq_llm
    except ImportError as exc:
        raise RuntimeError(
            "Groq provider requires the langchain-groq package."
        ) from exc

    return create_groq_llm(**settings)


def _create_ollama(**settings: Any) -> Any:
    """Load Ollama only when that provider is selected."""

    try:
        from ollama_llm import create_ollama_llm
    except ImportError as exc:
        raise RuntimeError(
            "Ollama provider requires the langchain-ollama package."
        ) from exc

    return create_ollama_llm(**settings)


def _create_openai(**settings: Any) -> Any:
    """Load OpenAI only when that provider is selected."""

    try:
        from openai_llm import create_openai_llm
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI provider requires the langchain-openai package."
        ) from exc

    return create_openai_llm(**settings)


_PROVIDER_MAP: dict[str, ProviderFactory] = {
    "groq": _create_groq,
    "ollama": _create_ollama,
    "openai": _create_openai,
}


@functools.lru_cache(maxsize=None)
def _get_raw_llm_cached(provider: str) -> Any:
    """Return a cached provider using YAML and environment settings."""

    settings = get_provider_settings(
        provider,
        _LLM_CONFIG,
    )

    return _PROVIDER_MAP[provider](**settings)


def clear_llm_cache() -> None:
    """Clear cached provider instances after configuration changes."""

    _get_raw_llm_cached.cache_clear()


def get_llm(
    provider: str | None = None,
    *,
    caller_id: str = "global",
    apply_rate_limit: bool = True,
    **overrides: Any,
) -> Any:
    """Return the configured language model.

    Args:
        provider: Ollama, Groq or OpenAI. Defaults to YAML/environment.
        caller_id: Identifier used for independent usage counters.
        apply_rate_limit: Disable only for controlled testing.
        overrides: Temporary provider or generation-setting overrides.
    """

    selected_provider = (
        provider
        or get_default_provider(_LLM_CONFIG)
    ).strip().lower()

    if selected_provider not in _PROVIDER_MAP:
        supported = ", ".join(sorted(_PROVIDER_MAP))

        raise ValueError(
            f"Unknown LLM provider '{selected_provider}'. "
            f"Supported providers: {supported}."
        )

    # Read normal model settings from YAML and local environment.
    model_settings = get_provider_settings(
        selected_provider,
        _LLM_CONFIG,
    )

    if overrides:
        model_settings.update(
            {
                key: value
                for key, value in overrides.items()
                if value is not None
            }
        )

        raw_llm = _PROVIDER_MAP[selected_provider](
            **model_settings
        )
    else:
        raw_llm = _get_raw_llm_cached(
            selected_provider
        )

    if not apply_rate_limit:
        return raw_llm

    provider_config = (
        _LLM_CONFIG
        .get("providers", {})
        .get(selected_provider, {})
    )

    input_price = float(
        provider_config.get(
            "input_cost_per_million_usd",
            0.0,
        )
    )

    output_price = float(
        provider_config.get(
            "output_cost_per_million_usd",
            0.0,
        )
    )

    max_output_tokens = int(
        model_settings.get(
            "max_tokens",
            1024,
        )
    )

    return apply_governance(
        raw_llm,
        caller_id=caller_id,
        provider=selected_provider,
        input_cost_per_million_usd=input_price,
        output_cost_per_million_usd=output_price,
        max_output_tokens=max_output_tokens,
    )