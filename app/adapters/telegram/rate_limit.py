"""Per-user token bucket for throttling expensive operations (currently only
photo uploads, which trigger OCR and potentially an AI call).

Kept deliberately simple: in-memory, single-process, no persistence. A user
who restarts the bot gets a fresh allowance; that's acceptable for the abuse
profile we're defending against (individual users hammering a single session).
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    last_refill_monotonic: float


class TokenBucketRateLimiter:
    """Classic token-bucket: a bucket refills at ``refill_per_second`` up to
    ``capacity`` tokens. Each successful :meth:`allow` call costs one token.

    Thread-safety: not required — the Telegram dispatcher serialises updates
    for a given user, and we never share a bucket across users.
    """

    def __init__(self, *, capacity: int, refill_per_second: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = float(capacity)
        self._refill_per_second = float(refill_per_second)
        self._buckets: dict[int, _Bucket] = {}

    def allow(self, user_id: int, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        bucket = self._buckets.get(user_id)
        if bucket is None:
            bucket = _Bucket(tokens=self._capacity, last_refill_monotonic=current)
            self._buckets[user_id] = bucket
        else:
            elapsed = max(0.0, current - bucket.last_refill_monotonic)
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_per_second)
            bucket.last_refill_monotonic = current
        if bucket.tokens < 1.0:
            return False
        bucket.tokens -= 1.0
        return True

    def remaining(self, user_id: int, *, now: float | None = None) -> float:
        """Exposed for diagnostics / tests."""
        bucket = self._buckets.get(user_id)
        if bucket is None:
            return self._capacity
        current = now if now is not None else time.monotonic()
        elapsed = max(0.0, current - bucket.last_refill_monotonic)
        return min(self._capacity, bucket.tokens + elapsed * self._refill_per_second)
