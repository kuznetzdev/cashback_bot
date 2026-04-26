"""Re-export of the shared token-bucket rate limiter.

Kept as a module-level import shim so existing callers keep working while the
canonical implementation lives in ``app.adapters.rate_limit`` (shared across
telegram and web adapters).
"""

from __future__ import annotations

from app.adapters.rate_limit import TokenBucketRateLimiter

__all__ = ["TokenBucketRateLimiter"]
