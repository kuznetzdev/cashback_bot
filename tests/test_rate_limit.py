from __future__ import annotations

import pytest

from app.adapters.telegram.rate_limit import TokenBucketRateLimiter


def test_fresh_user_can_burn_full_capacity() -> None:
    limiter = TokenBucketRateLimiter(capacity=3, refill_per_second=1.0)
    # 3 photos allowed immediately.
    assert limiter.allow(user_id=1, now=0.0)
    assert limiter.allow(user_id=1, now=0.0)
    assert limiter.allow(user_id=1, now=0.0)
    # 4th is denied — bucket empty.
    assert not limiter.allow(user_id=1, now=0.0)


def test_tokens_refill_over_time() -> None:
    limiter = TokenBucketRateLimiter(capacity=3, refill_per_second=1.0)
    for _ in range(3):
        limiter.allow(user_id=1, now=0.0)
    assert not limiter.allow(user_id=1, now=0.0)
    # After 2 seconds of waiting, 2 tokens refilled → 2 photos allowed.
    assert limiter.allow(user_id=1, now=2.0)
    assert limiter.allow(user_id=1, now=2.0)
    assert not limiter.allow(user_id=1, now=2.0)


def test_refill_caps_at_capacity() -> None:
    limiter = TokenBucketRateLimiter(capacity=3, refill_per_second=1.0)
    limiter.allow(user_id=1, now=0.0)  # Bucket at 2.
    # 10 seconds pass — but capacity caps at 3, not 12.
    for _ in range(3):
        assert limiter.allow(user_id=1, now=10.0)
    assert not limiter.allow(user_id=1, now=10.0)


def test_buckets_are_per_user() -> None:
    limiter = TokenBucketRateLimiter(capacity=2, refill_per_second=1.0)
    # User 1 exhausts their bucket…
    limiter.allow(user_id=1, now=0.0)
    limiter.allow(user_id=1, now=0.0)
    assert not limiter.allow(user_id=1, now=0.0)
    # …but user 2 is unaffected.
    assert limiter.allow(user_id=2, now=0.0)
    assert limiter.allow(user_id=2, now=0.0)
    assert not limiter.allow(user_id=2, now=0.0)


def test_remaining_reports_live_token_count() -> None:
    limiter = TokenBucketRateLimiter(capacity=5, refill_per_second=0.5)
    limiter.allow(user_id=1, now=0.0)  # Bucket: 4.
    assert limiter.remaining(user_id=1, now=0.0) == pytest.approx(4.0)
    # 4 seconds later: refilled by 2.0 tokens → 5 (capped at capacity).
    assert limiter.remaining(user_id=1, now=4.0) == pytest.approx(5.0)


def test_fresh_user_remaining_reports_full_capacity() -> None:
    # Users we have never seen before must report as fully available —
    # otherwise the /top "has this user uploaded anything?" surface would
    # give misleading numbers.
    limiter = TokenBucketRateLimiter(capacity=7, refill_per_second=1.0)
    assert limiter.remaining(user_id=999, now=123.0) == pytest.approx(7.0)


def test_zero_or_negative_capacity_rejected() -> None:
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=0, refill_per_second=1.0)
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=-1, refill_per_second=1.0)


def test_non_positive_refill_rejected() -> None:
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=1, refill_per_second=0)
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=1, refill_per_second=-0.5)
