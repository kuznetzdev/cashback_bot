"""Tiny in-memory circuit breaker.

Wraps any callable that may fail transiently (network call to OpenAI,
Telegram, etc.) and trips after ``failure_threshold`` consecutive errors.
While tripped, every call returns immediately without invoking the inner
callable, until ``cool_down_seconds`` elapse and the breaker enters
half-open state — the next call probes the dependency and either closes
the breaker on success or re-opens it on failure.

Why local: this lives in-process, single-replica. Multi-replica
deployments need an external coordination layer (Redis, Hazelcast); for
our scale and the specific use case (an OpenAI 429 storm shouldn't burn
your bill while waiting out the rate window), an in-process breaker is
sufficient and stays out of the request critical path.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)


T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when a call is short-circuited by an open breaker."""


@dataclass
class CircuitBreakerStats:
    """Diagnostics — exposed to tests and ops dashboards."""
    state: str = "closed"               # "closed" | "open" | "half_open"
    consecutive_failures: int = 0
    opened_at: float | None = None
    last_failure_reason: str | None = None
    trips: int = 0
    successes_since_close: int = 0


class CircuitBreaker(Generic[T]):
    """Trip after ``failure_threshold`` consecutive failures, stay open for
    ``cool_down_seconds``, then probe with one call (half-open). Counts both
    exceptions and the optional ``is_failure`` predicate (e.g. ``None``
    return value) as failures."""

    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int = 5,
        cool_down_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if cool_down_seconds <= 0:
            raise ValueError("cool_down_seconds must be positive")
        self._name = name
        self._failure_threshold = failure_threshold
        self._cool_down = float(cool_down_seconds)
        self._clock = clock
        self._lock = asyncio.Lock()
        self._stats = CircuitBreakerStats()

    @property
    def state(self) -> str:
        return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        is_failure: Callable[[T], bool] | None = None,
        **kwargs: object,
    ) -> T:
        """Invoke ``func``. Returns the result on success, re-raises on
        exception, raises :class:`CircuitOpenError` when the breaker is
        currently open. ``is_failure`` lets callers treat specific return
        values as failures without raising (useful for batch APIs)."""
        async with self._lock:
            self._maybe_close_after_cool_down()
            if self._stats.state == "open":
                raise CircuitOpenError(
                    f"{self._name} circuit is open until "
                    f"{self._stats.opened_at + self._cool_down:.1f}"
                )

        try:
            result = await func(*args, **kwargs)
        except Exception as error:
            await self._record_failure(repr(error))
            raise

        if is_failure is not None and is_failure(result):
            await self._record_failure("predicate matched")
            return result
        await self._record_success()
        return result

    def _maybe_close_after_cool_down(self) -> None:
        if self._stats.state != "open":
            return
        opened_at = self._stats.opened_at or 0.0
        if self._clock() - opened_at >= self._cool_down:
            # Move to half-open: next call probes; on success we fully
            # close, on failure we trip back to open with a fresh timer.
            self._stats.state = "half_open"
            logger.info("Circuit %s half-open — probing", self._name)

    async def _record_failure(self, reason: str) -> None:
        async with self._lock:
            self._stats.consecutive_failures += 1
            self._stats.last_failure_reason = reason
            should_trip = (
                self._stats.state == "half_open"
                or self._stats.consecutive_failures >= self._failure_threshold
            )
            if should_trip and self._stats.state != "open":
                self._stats.state = "open"
                self._stats.opened_at = self._clock()
                self._stats.trips += 1
                self._stats.successes_since_close = 0
                logger.warning(
                    "Circuit %s tripped after %s consecutive failures (last: %s)",
                    self._name,
                    self._stats.consecutive_failures,
                    reason,
                )

    async def _record_success(self) -> None:
        async with self._lock:
            if self._stats.state in ("half_open", "open"):
                logger.info("Circuit %s closed after probe success", self._name)
            self._stats.state = "closed"
            self._stats.consecutive_failures = 0
            self._stats.opened_at = None
            self._stats.successes_since_close += 1
