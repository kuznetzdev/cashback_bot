from __future__ import annotations

from app.bootstrap.metrics import MetricsRegistry


def test_observe_user_does_not_double_count_repeat_visits() -> None:
    metrics = MetricsRegistry(max_tracked_users=1000)
    for _ in range(5):
        metrics.observe_user(42)
    # The user is only counted once, regardless of how many updates they send.
    assert len(metrics._seen_users) == 1


def test_observe_user_evicts_lru_when_capacity_exceeded() -> None:
    metrics = MetricsRegistry(max_tracked_users=3)
    for user_id in (1, 2, 3, 4, 5):
        metrics.observe_user(user_id)
    # Cap is 3. After observing 5 distinct users, the two oldest (1 and 2)
    # must have been evicted; 3, 4, 5 remain.
    assert len(metrics._seen_users) == 3
    assert set(metrics._seen_users.keys()) == {3, 4, 5}


def test_observe_user_touch_keeps_user_alive() -> None:
    metrics = MetricsRegistry(max_tracked_users=3)
    metrics.observe_user(1)
    metrics.observe_user(2)
    metrics.observe_user(3)
    # Re-touch user 1 — should move them to MRU.
    metrics.observe_user(1)
    metrics.observe_user(4)
    # User 2 (now LRU) is the one that gets evicted, not user 1.
    assert set(metrics._seen_users.keys()) == {1, 3, 4}


def test_max_tracked_users_normalises_zero_and_negative() -> None:
    # The implementation should never produce a 0-capacity LRU since that
    # would break observe_user (popitem on an empty dict).
    metrics = MetricsRegistry(max_tracked_users=0)
    metrics.observe_user(1)
    assert len(metrics._seen_users) == 1
