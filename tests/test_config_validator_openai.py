"""Regression tests for OpenAI support in startup configuration validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "1.5_security" / "config_validator.py"
SPEC = importlib.util.spec_from_file_location("cybernexa_config_validator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
config_validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = config_validator
SPEC.loader.exec_module(config_validator)


def _valid_common_config() -> dict[str, str]:
    return {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test-not-a-real-key",
        "OPENAI_MODEL": "gpt-5-mini",
        "LLM_TEMPERATURE": "0.1",
        "LLM_MAX_TOKENS": "1024",
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_REQUESTS": "10",
        "RATE_LIMIT_WINDOW_SECONDS": "60",
        "LLM_DAILY_REQUEST_LIMIT": "250",
    }


def test_openai_provider_is_accepted() -> None:
    result = config_validator.validate_environment(_valid_common_config())
    assert result.ok, result.errors


def test_openai_api_key_is_required() -> None:
    config = _valid_common_config()
    config.pop("OPENAI_API_KEY")
    result = config_validator.validate_environment(config)
    assert "OPENAI_API_KEY is missing or still contains a placeholder." in result.errors


def test_openai_model_is_required() -> None:
    config = _valid_common_config()
    config.pop("OPENAI_MODEL")
    result = config_validator.validate_environment(config)
    assert "OPENAI_MODEL is missing or still contains a placeholder." in result.errors
