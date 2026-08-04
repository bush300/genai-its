"""Startup configuration validation for CyberNexa / GenAI ITS.

Run locally:
    python 1.5_security/config_validator.py

Validate the committed example templates (safe for CI):
    python 1.5_security/config_validator.py --check-example
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
SECRETS_FILE = PROJECT_ROOT / ".streamlit" / "secrets.toml"
SECRETS_EXAMPLE = PROJECT_ROOT / ".streamlit" / "secrets.example.toml"


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized.startswith("replace_")
        or normalized.startswith("your-")
        or normalized.startswith("your_")
        or "your_" in normalized
        or "your-" in normalized
        or "placeholder" in normalized
    )


def _positive_int(config: Mapping[str, str | None], name: str, result: ValidationResult) -> None:
    value = config.get(name)
    if value is None or str(value).strip() == "":
        result.errors.append(f"{name} is missing.")
        return
    try:
        parsed = int(str(value))
        if parsed <= 0:
            raise ValueError
    except ValueError:
        result.errors.append(f"{name} must be a positive integer.")


def _float_range(
    config: Mapping[str, str | None],
    name: str,
    minimum: float,
    maximum: float,
    result: ValidationResult,
) -> None:
    value = config.get(name)
    if value is None or str(value).strip() == "":
        result.errors.append(f"{name} is missing.")
        return
    try:
        parsed = float(str(value))
    except ValueError:
        result.errors.append(f"{name} must be a number.")
        return
    if not minimum <= parsed <= maximum:
        result.errors.append(f"{name} must be between {minimum} and {maximum}.")


def validate_environment(config: Mapping[str, str | None], allow_placeholders: bool = False) -> ValidationResult:
    result = ValidationResult()
    provider = str(config.get("LLM_PROVIDER", "groq")).strip().lower()

    if provider not in {"groq", "ollama", "openai"}:
        result.errors.append("LLM_PROVIDER must be 'groq', 'ollama', or 'openai'.")

    if provider == "groq":
        api_key = config.get("GROQ_API_KEY")
        if not api_key or (not allow_placeholders and _is_placeholder(str(api_key))):
            result.errors.append("GROQ_API_KEY is missing or still contains a placeholder.")
        model = config.get("GROQ_MODEL")
        if not model or (not allow_placeholders and _is_placeholder(str(model))):
            result.errors.append("GROQ_MODEL is missing or still contains a placeholder.")

    if provider == "openai":
        api_key = config.get("OPENAI_API_KEY")
        if not api_key or (not allow_placeholders and _is_placeholder(str(api_key))):
            result.errors.append("OPENAI_API_KEY is missing or still contains a placeholder.")
        model = config.get("OPENAI_MODEL")
        if not model or (not allow_placeholders and _is_placeholder(str(model))):
            result.errors.append("OPENAI_MODEL is missing or still contains a placeholder.")

    if provider == "ollama":
        model = config.get("OLLAMA_MODEL")
        if not model or (not allow_placeholders and _is_placeholder(str(model))):
            result.errors.append("OLLAMA_MODEL is missing or still contains a placeholder.")
        base_url = str(config.get("OLLAMA_BASE_URL", "")).strip()
        if not base_url.startswith(("http://", "https://")):
            result.errors.append("OLLAMA_BASE_URL must begin with http:// or https://.")

    _float_range(config, "LLM_TEMPERATURE", 0.0, 2.0, result)
    _positive_int(config, "LLM_MAX_TOKENS", result)

    rate_limit_enabled = str(config.get("RATE_LIMIT_ENABLED", "true")).strip().lower()
    if rate_limit_enabled not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        result.errors.append("RATE_LIMIT_ENABLED must be true or false.")
    if rate_limit_enabled in {"true", "1", "yes", "on"}:
        _positive_int(config, "RATE_LIMIT_REQUESTS", result)
        _positive_int(config, "RATE_LIMIT_WINDOW_SECONDS", result)
        _positive_int(config, "LLM_DAILY_REQUEST_LIMIT", result)

    return result


def validate_firebase_secrets(path: Path, allow_placeholders: bool = False) -> ValidationResult:
    result = ValidationResult()
    if not path.exists():
        result.errors.append(f"Firebase secrets file not found: {path}")
        return result

    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive startup validation
        result.errors.append(f"Could not read Firebase secrets: {exc}")
        return result

    firebase = data.get("FIREBASE")
    if not isinstance(firebase, dict):
        result.errors.append("The secrets file must contain a [FIREBASE] section.")
        return result

    required = {
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "client_id",
        "auth_uri",
        "token_uri",
    }
    for key in sorted(required):
        value = firebase.get(key)
        if not value:
            result.errors.append(f"FIREBASE.{key} is missing.")
        elif not allow_placeholders and _is_placeholder(str(value)):
            result.errors.append(f"FIREBASE.{key} still contains a placeholder.")

    return result


def _merge(target: ValidationResult, source: ValidationResult) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)


def validate_runtime(require_firebase: bool = True) -> ValidationResult:
    load_dotenv(ENV_FILE)
    result = validate_environment(os.environ)
    if require_firebase:
        _merge(result, validate_firebase_secrets(SECRETS_FILE))
    return result


def validate_examples() -> ValidationResult:
    result = ValidationResult()
    if not ENV_EXAMPLE.exists():
        result.errors.append(".env.example is missing.")
    else:
        values = dotenv_values(ENV_EXAMPLE)
        _merge(result, validate_environment(values, allow_placeholders=True))

    _merge(result, validate_firebase_secrets(SECRETS_EXAMPLE, allow_placeholders=True))
    return result


def print_result(result: ValidationResult) -> None:
    if result.ok:
        print("[OK] Configuration validation passed.")
    for warning in result.warnings:
        print(f"[WARNING] {warning}")
    for error in result.errors:
        print(f"[ERROR] {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CyberNexa configuration safely.")
    parser.add_argument(
        "--check-example",
        action="store_true",
        help="Validate committed example templates without requiring real secrets.",
    )
    parser.add_argument(
        "--skip-firebase",
        action="store_true",
        help="Validate only the LLM/rate-limit environment configuration.",
    )
    args = parser.parse_args()

    result = validate_examples() if args.check_example else validate_runtime(not args.skip_firebase)
    print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
