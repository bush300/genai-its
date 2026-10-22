"""Shared YAML configuration loader for LLM routing and governance.

Author: Saad
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "llm_config.yaml"


class LLMConfigurationError(RuntimeError):
    """Raised when the shared LLM configuration is missing or invalid."""


@lru_cache(maxsize=1)
def load_llm_config(
    config_path: str | None = None,
) -> dict[str, Any]:
    """Load and validate the shared YAML configuration."""

    path = (
        Path(config_path).resolve()
        if config_path
        else DEFAULT_CONFIG_PATH
    )

    if not path.exists():
        raise LLMConfigurationError(
            f"LLM configuration file was not found: {path}"
        )

    try:
        config = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )
    except yaml.YAMLError as exc:
        raise LLMConfigurationError(
            f"LLM configuration contains invalid YAML: {path}"
        ) from exc

    if not isinstance(config, dict):
        raise LLMConfigurationError(
            "LLM configuration must contain a YAML mapping."
        )

    providers = config.get("providers")

    if not isinstance(providers, dict) or not providers:
        raise LLMConfigurationError(
            "LLM configuration must define at least one provider."
        )

    return config


def get_default_provider(
    config: dict[str, Any] | None = None,
) -> str:
    """Return the provider selected by environment or YAML."""

    loaded_config = config or load_llm_config()
    routing = loaded_config.get("routing") or {}

    allow_environment_override = bool(
        routing.get("allow_environment_override", True)
    )

    environment_provider = os.getenv(
        "LLM_PROVIDER",
        "",
    ).strip().lower()

    if allow_environment_override and environment_provider:
        return environment_provider

    return str(
        routing.get("default_provider", "groq")
    ).strip().lower()


def get_provider_settings(
    provider: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return merged YAML and environment settings for one provider."""

    loaded_config = config or load_llm_config()
    providers = loaded_config.get("providers") or {}

    selected_provider = provider.strip().lower()

    if selected_provider not in providers:
        supported = ", ".join(sorted(providers))

        raise LLMConfigurationError(
            f"Unknown LLM provider '{selected_provider}'. "
            f"Configured providers: {supported}."
        )

    provider_config = providers[selected_provider]

    if not isinstance(provider_config, dict):
        raise LLMConfigurationError(
            f"Provider '{selected_provider}' has invalid configuration."
        )

    if not provider_config.get("enabled", True):
        raise LLMConfigurationError(
            f"Provider '{selected_provider}' is disabled in "
            "config/llm_config.yaml."
        )

    generation = loaded_config.get("generation") or {}
    settings: dict[str, Any] = {}

    model_environment_name = (
        f"{selected_provider.upper()}_MODEL"
    )

    model = (
        os.getenv(model_environment_name)
        or provider_config.get("model")
    )

    if model:
        settings["model_name"] = str(model)

    if selected_provider == "ollama":
        base_url = (
            os.getenv("OLLAMA_BASE_URL")
            or provider_config.get("base_url")
        )

        if base_url:
            settings["base_url"] = str(base_url)

    api_key_environment_name = provider_config.get(
        "api_key_env"
    )

    if api_key_environment_name:
        api_key = os.getenv(
            str(api_key_environment_name)
        )

        if api_key:
            settings["api_key"] = api_key

    temperature = os.getenv(
        "LLM_TEMPERATURE",
        str(generation.get("temperature", 0.1)),
    )

    max_tokens = os.getenv(
        "LLM_MAX_TOKENS",
        str(generation.get("max_tokens", 1024)),
    )

    settings["temperature"] = float(temperature)
    settings["max_tokens"] = int(max_tokens)

    return settings


def apply_governance_environment(
    config: dict[str, Any] | None = None,
) -> None:
    """Expose YAML governance settings to the existing rate limiter."""

    loaded_config = config or load_llm_config()
    governance = loaded_config.get("governance") or {}

    values = {
        "RATE_LIMIT_ENABLED": governance.get(
            "rate_limit_enabled",
            True,
        ),
        "RATE_LIMIT_REQUESTS": governance.get(
            "requests_per_window",
            10,
        ),
        "RATE_LIMIT_WINDOW_SECONDS": governance.get(
            "window_seconds",
            60,
        ),
        "LLM_DAILY_REQUEST_LIMIT": governance.get(
            "daily_request_limit",
            250,
        ),
        "LLM_DAILY_BUDGET_USD": governance.get(
            "daily_budget_usd",
            1.0,
        ),
    }

    for environment_name, value in values.items():
        if isinstance(value, bool):
            environment_value = str(value).lower()
        else:
            environment_value = str(value)

        os.environ.setdefault(
            environment_name,
            environment_value,
        )


def clear_llm_config_cache() -> None:
    """Reload the YAML file during tests or configuration changes."""

    load_llm_config.cache_clear()