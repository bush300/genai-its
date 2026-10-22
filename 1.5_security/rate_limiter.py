"""In-memory request-rate, daily-budget and token-cost controls for LLM calls.

Author: Saad

This is intentionally lightweight for the A4 prototype. In a multi-server
production system, counters should be moved to a shared store such as Redis
or Firestore.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Any

from audit_logger import audit_logger


LOGGER = logging.getLogger(__name__)


def _audit_safely(
    *,
    event_type: str,
    message: str,
    severity: str = "INFO",
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an audit event without interrupting the application."""

    try:
        audit_logger.log_event(
            event_type=event_type,
            message=message,
            severity=severity,
            user_id=user_id,
            source_module="rate_limiter",
            metadata=metadata or {},
        )
    except Exception:
        LOGGER.exception(
            "The audit event could not be recorded."
        )


class RateLimitExceeded(RuntimeError):
    """Raised when too many requests are made in the configured time window."""


class DailyBudgetExceeded(RuntimeError):
    """Raised when the configured daily request or cost budget is reached."""


def _as_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class GovernanceConfig:
    enabled: bool
    requests: int
    window_seconds: int
    daily_request_limit: int
    daily_budget_usd: float = 1.0

    @classmethod
    def from_environment(cls) -> "GovernanceConfig":
        return cls(
            enabled=_as_bool(
                os.getenv("RATE_LIMIT_ENABLED"),
                True,
            ),
            requests=max(
                1,
                int(os.getenv("RATE_LIMIT_REQUESTS", "10")),
            ),
            window_seconds=max(
                1,
                int(
                    os.getenv(
                        "RATE_LIMIT_WINDOW_SECONDS",
                        "60",
                    )
                ),
            ),
            daily_request_limit=max(
                1,
                int(
                    os.getenv(
                        "LLM_DAILY_REQUEST_LIMIT",
                        "250",
                    )
                ),
            ),
            daily_budget_usd=max(
                0.0,
                float(
                    os.getenv(
                        "LLM_DAILY_BUDGET_USD",
                        "1.00",
                    )
                ),
            ),
        )


class UsageGovernor:
    def __init__(
        self,
        config: GovernanceConfig | None = None,
    ) -> None:
        self.config = (
            config
            or GovernanceConfig.from_environment()
        )

        self._requests: dict[
            str,
            deque[float],
        ] = defaultdict(deque)

        self._daily_counts: dict[
            tuple[str, str],
            int,
        ] = defaultdict(int)

        self._daily_costs: dict[
            tuple[str, str],
            float,
        ] = defaultdict(float)

        self._lock = threading.Lock()

    def check_and_record(
        self,
        caller_id: str = "global",
        estimated_cost_usd: float = 0.0,
    ) -> None:
        """Check limits before allowing an AI request."""

        if not self.config.enabled:
            return

        now = time.monotonic()
        today = date.today().isoformat()
        cutoff = now - self.config.window_seconds

        estimated_cost = max(
            0.0,
            float(estimated_cost_usd),
        )

        with self._lock:
            request_times = self._requests[caller_id]

            while (
                request_times
                and request_times[0] <= cutoff
            ):
                request_times.popleft()

            if len(request_times) >= self.config.requests:
                retry_after = max(
                    1,
                    int(
                        request_times[0]
                        + self.config.window_seconds
                        - now
                    )
                    + 1,
                )

                _audit_safely(
                    event_type="rate_limit_hit",
                    severity="WARNING",
                    user_id=caller_id,
                    message="Request-window rate limit exceeded.",
                    metadata={
                        "limit_type": "request_window",
                        "request_limit": self.config.requests,
                        "window_seconds": self.config.window_seconds,
                        "retry_after_seconds": retry_after,
                    },
                )

                raise RateLimitExceeded(
                    "Request limit reached. Please wait "
                    f"approximately {retry_after} second(s) "
                    "before trying again."
                )

            daily_key = (
                caller_id,
                today,
            )

            if (
                self._daily_counts[daily_key]
                >= self.config.daily_request_limit
            ):
                _audit_safely(
                    event_type="rate_limit_hit",
                    severity="WARNING",
                    user_id=caller_id,
                    message="Daily AI request limit exceeded.",
                    metadata={
                        "limit_type": "daily_request",
                        "daily_request_limit": (
                            self.config.daily_request_limit
                        ),
                        "daily_requests_used": (
                            self._daily_counts[daily_key]
                        ),
                    },
                )

                raise DailyBudgetExceeded(
                    "The daily AI request limit has been "
                    "reached. Please contact the system "
                    "administrator or try again tomorrow."
                )

            current_cost = self._daily_costs[daily_key]

            projected_cost = (
                current_cost
                + estimated_cost
            )

            if (
                self.config.daily_budget_usd > 0
                and projected_cost
                > self.config.daily_budget_usd
            ):
                _audit_safely(
                    event_type="rate_limit_hit",
                    severity="WARNING",
                    user_id=caller_id,
                    message="Daily AI cost budget exceeded.",
                    metadata={
                        "limit_type": "daily_cost",
                        "daily_budget_usd": (
                            self.config.daily_budget_usd
                        ),
                        "projected_cost_usd": round(
                            projected_cost,
                            6,
                        ),
                    },
                )

                raise DailyBudgetExceeded(
                    "The estimated cost of this AI request "
                    "would exceed the daily budget of "
                    f"${self.config.daily_budget_usd:.2f}. "
                    "Please select the local Ollama provider "
                    "or try again tomorrow."
                )

            request_times.append(now)
            self._daily_counts[daily_key] += 1

    def record_cost(
        self,
        caller_id: str,
        cost_usd: float,
    ) -> None:
        """Record provider cost after a successful request."""

        if not self.config.enabled:
            return

        today = date.today().isoformat()

        daily_key = (
            caller_id,
            today,
        )

        with self._lock:
            self._daily_costs[daily_key] += max(
                0.0,
                float(cost_usd),
            )

    def snapshot(
        self,
        caller_id: str = "global",
    ) -> dict[str, int | float | bool]:
        """Return current usage and cost information."""

        today = date.today().isoformat()

        daily_key = (
            caller_id,
            today,
        )

        with self._lock:
            return {
                "enabled": self.config.enabled,
                "window_request_limit": (
                    self.config.requests
                ),
                "window_seconds": (
                    self.config.window_seconds
                ),
                "daily_request_limit": (
                    self.config.daily_request_limit
                ),
                "daily_requests_used": (
                    self._daily_counts[daily_key]
                ),
                "daily_budget_usd": round(
                    self.config.daily_budget_usd,
                    6,
                ),
                "daily_cost_used_usd": round(
                    self._daily_costs[daily_key],
                    6,
                ),
            }


_DEFAULT_GOVERNOR = UsageGovernor()


def _content_to_text(value: Any) -> str:
    """Convert LangChain inputs and outputs into text."""

    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return " ".join(
            _content_to_text(item)
            for item in value.values()
        )

    if isinstance(value, (list, tuple)):
        return " ".join(
            _content_to_text(item)
            for item in value
        )

    content = getattr(
        value,
        "content",
        None,
    )

    if content is not None:
        return _content_to_text(content)

    return str(value)


def _estimate_tokens(value: Any) -> int:
    """Estimate tokens using four characters per token."""

    text = _content_to_text(value)

    if not text:
        return 0

    return max(
        1,
        math.ceil(len(text) / 4),
    )


def _extract_token_usage(
    response: Any,
) -> tuple[int, int]:
    """Read LangChain or provider token metadata."""

    usage = getattr(
        response,
        "usage_metadata",
        None,
    )

    if isinstance(usage, dict):
        input_tokens = int(
            usage.get("input_tokens")
            or usage.get("prompt_tokens")
            or 0
        )

        output_tokens = int(
            usage.get("output_tokens")
            or usage.get("completion_tokens")
            or 0
        )

        if input_tokens or output_tokens:
            return (
                input_tokens,
                output_tokens,
            )

    response_metadata = getattr(
        response,
        "response_metadata",
        None,
    )

    if isinstance(response_metadata, dict):
        token_usage = (
            response_metadata.get("token_usage")
            or response_metadata.get("usage")
            or {}
        )

        if isinstance(token_usage, dict):
            input_tokens = int(
                token_usage.get("input_tokens")
                or token_usage.get("prompt_tokens")
                or 0
            )

            output_tokens = int(
                token_usage.get("output_tokens")
                or token_usage.get(
                    "completion_tokens"
                )
                or 0
            )

            if input_tokens or output_tokens:
                return (
                    input_tokens,
                    output_tokens,
                )

    return 0, 0


# ---------------------------------------------------------------------------
# FR14 - Egress controls and sensitive-data masking
# ---------------------------------------------------------------------------

_CLOUD_PROVIDERS = {
    "groq",
    "openai",
}

_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

_STUDENT_ID_PATTERN = re.compile(
    r"\b("
    r"(?:student[\s_-]*id|student\s+number)"
    r"\s*(?::|=|\bis\b)\s*"
    r")"
    r"([A-Za-z0-9][A-Za-z0-9_-]*)",
    re.IGNORECASE,
)


def _mask_sensitive_text(text: str) -> str:
    """Mask sensitive information before cloud LLM requests."""

    masked = _EMAIL_PATTERN.sub(
        "[REDACTED_EMAIL]",
        text,
    )

    masked = _STUDENT_ID_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}"
            "[REDACTED_STUDENT_ID]"
        ),
        masked,
    )

    return masked


def _mask_sensitive_request(value: Any) -> Any:
    """Mask sensitive text while preserving common request structures."""

    if isinstance(value, str):
        return _mask_sensitive_text(value)

    if isinstance(value, list):
        return [
            _mask_sensitive_request(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return tuple(
            _mask_sensitive_request(item)
            for item in value
        )

    if isinstance(value, dict):
        return {
            key: _mask_sensitive_request(item)
            for key, item in value.items()
        }

    return value


class GovernedLLM:
    """Proxy that applies request, cost and egress governance."""

    def __init__(
        self,
        llm: Any,
        caller_id: str = "global",
        governor: UsageGovernor | None = None,
        *,
        provider: str = "unknown",
        input_cost_per_million_usd: float = 0.0,
        output_cost_per_million_usd: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> None:
        self._llm = llm
        self._caller_id = caller_id
        self._governor = (
            governor
            or _DEFAULT_GOVERNOR
        )

        self._provider = (
            str(provider)
            .strip()
            .lower()
        )

        self._input_cost_per_million_usd = max(
            0.0,
            float(input_cost_per_million_usd),
        )

        self._output_cost_per_million_usd = max(
            0.0,
            float(output_cost_per_million_usd),
        )

        self._max_output_tokens = max(
            0,
            int(max_output_tokens),
        )

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        input_cost = (
            max(0, input_tokens)
            / 1_000_000
            * self._input_cost_per_million_usd
        )

        output_cost = (
            max(0, output_tokens)
            / 1_000_000
            * self._output_cost_per_million_usd
        )

        return input_cost + output_cost

    def _estimated_request_cost(
        self,
        request: Any,
    ) -> float:
        return self._calculate_cost(
            _estimate_tokens(request),
            self._max_output_tokens,
        )

    def _record_response_cost(
        self,
        request: Any,
        response: Any,
    ) -> None:
        input_tokens, output_tokens = (
            _extract_token_usage(response)
        )

        if not input_tokens:
            input_tokens = _estimate_tokens(
                request
            )

        if not output_tokens:
            output_tokens = _estimate_tokens(
                getattr(
                    response,
                    "content",
                    response,
                )
            )

        self._governor.record_cost(
            self._caller_id,
            self._calculate_cost(
                input_tokens,
                output_tokens,
            ),
        )

    def _prepare_outbound_request(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> tuple[
        tuple[Any, ...],
        dict[str, Any],
        Any,
    ]:
        """Prepare a request before it is sent to the provider."""

        request = (
            args[0]
            if args
            else kwargs.get("input")
        )

        outbound_args = args
        outbound_kwargs = kwargs

        if self._provider not in _CLOUD_PROVIDERS:
            return (
                outbound_args,
                outbound_kwargs,
                request,
            )

        masked_request = _mask_sensitive_request(
            request
        )

        if args:
            outbound_args = (
                masked_request,
                *args[1:],
            )

        elif "input" in kwargs:
            outbound_kwargs = dict(kwargs)
            outbound_kwargs["input"] = (
                masked_request
            )

        return (
            outbound_args,
            outbound_kwargs,
            request,
        )

    def invoke(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        (
            outbound_args,
            outbound_kwargs,
            request,
        ) = self._prepare_outbound_request(
            args,
            kwargs,
        )

        self._governor.check_and_record(
            self._caller_id,
            estimated_cost_usd=(
                self._estimated_request_cost(
                    request
                )
            ),
        )

        try:
            response = self._llm.invoke(
                *outbound_args,
                **outbound_kwargs,
            )

        except Exception as exc:
            _audit_safely(
                event_type="system_error",
                severity="ERROR",
                user_id=self._caller_id,
                message="LLM provider invocation failed.",
                metadata={
                    "provider": self._provider,
                    "operation": "invoke",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        self._record_response_cost(
            request,
            response,
        )

        _audit_safely(
            event_type="llm_api_call",
            severity="INFO",
            user_id=self._caller_id,
            message="LLM provider invocation completed.",
            metadata={
                "provider": self._provider,
                "operation": "invoke",
                "successful": True,
            },
        )

        return response

    async def ainvoke(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        (
            outbound_args,
            outbound_kwargs,
            request,
        ) = self._prepare_outbound_request(
            args,
            kwargs,
        )

        self._governor.check_and_record(
            self._caller_id,
            estimated_cost_usd=(
                self._estimated_request_cost(
                    request
                )
            ),
        )

        try:
            response = await self._llm.ainvoke(
                *outbound_args,
                **outbound_kwargs,
            )

        except Exception as exc:
            _audit_safely(
                event_type="system_error",
                severity="ERROR",
                user_id=self._caller_id,
                message="Async LLM provider invocation failed.",
                metadata={
                    "provider": self._provider,
                    "operation": "ainvoke",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        self._record_response_cost(
            request,
            response,
        )

        _audit_safely(
            event_type="llm_api_call",
            severity="INFO",
            user_id=self._caller_id,
            message="Async LLM provider invocation completed.",
            metadata={
                "provider": self._provider,
                "operation": "ainvoke",
                "successful": True,
            },
        )

        return response

    def __getattr__(
        self,
        name: str,
    ) -> Any:
        return getattr(
            self._llm,
            name,
        )


def apply_governance(
    llm: Any,
    caller_id: str = "global",
    *,
    provider: str = "unknown",
    input_cost_per_million_usd: float = 0.0,
    output_cost_per_million_usd: float = 0.0,
    max_output_tokens: int = 1024,
) -> GovernedLLM:
    """Wrap an LLM with request and cost governance."""

    return GovernedLLM(
        llm,
        caller_id=caller_id,
        provider=provider,
        input_cost_per_million_usd=(
            input_cost_per_million_usd
        ),
        output_cost_per_million_usd=(
            output_cost_per_million_usd
        ),
        max_output_tokens=max_output_tokens,
    )


def get_usage_snapshot(
    caller_id: str = "global",
) -> dict[str, int | float | bool]:
    """Return usage and cost information for one caller."""

    return _DEFAULT_GOVERNOR.snapshot(
        caller_id
    )