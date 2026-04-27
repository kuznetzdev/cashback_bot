"""Shared Prometheus metrics registry.

Historically the metrics lived inside ``app/adapters/web/app.py`` — fine
while only the LoggingMiddleware fed them. As soon as other layers (OCR
adapters, scheduler) want to record counts, a shared module makes more
sense: all counters/histograms live here and the web app just renders
the same registry.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

logger = logging.getLogger(__name__)


# Cap how many distinct user_ids the active-users tracker remembers. The
# previous unbounded set would grow to ~8 bytes-per-int + dict overhead
# for every user the bot ever sees, leaking ~30 MiB per million users
# until the next process restart. With an LRU we stay capped at a
# bounded amount of memory and the gauge becomes "distinct users in the
# last `_MAX_TRACKED_USERS` seen", which is the more honest metric anyway.
_MAX_TRACKED_USERS = 50_000


class MetricsRegistry:
    """Typed wrapper around the Prometheus collector registry.

    Instantiate once at process start (in ``runtime.run_app``), share the
    instance with every adapter that needs to record samples, and expose
    ``.registry`` to the Prometheus exposition endpoint.
    """

    def __init__(self, *, max_tracked_users: int = _MAX_TRACKED_USERS) -> None:
        from prometheus_client import (
            CollectorRegistry,
            Counter,
            Gauge,
            Histogram,
        )

        self.registry: CollectorRegistry = CollectorRegistry(auto_describe=True)
        self.requests_total: Counter = Counter(
            "cashback_bot_requests_total",
            "Handler invocations by handler and status",
            ["handler", "status"],
            registry=self.registry,
        )
        self.request_duration: Histogram = Histogram(
            "cashback_bot_request_duration_seconds",
            "Handler latency distribution",
            ["handler"],
            registry=self.registry,
        )
        self.ocr_calls_total: Counter = Counter(
            "cashback_bot_ocr_calls_total",
            "OCR calls by provider and result",
            ["provider", "result"],
            registry=self.registry,
        )
        self.active_users: Gauge = Gauge(
            "cashback_bot_active_users_total",
            "Unique users seen in the recent window (LRU-bounded)",
            registry=self.registry,
        )
        # OrderedDict-as-LRU: insertion order = touch order, popitem(last=False)
        # evicts the oldest. Values are unused — only keys matter.
        self._seen_users: OrderedDict[int, None] = OrderedDict()
        self._max_tracked_users = max(1, max_tracked_users)

    def observe_user(self, user_id: int) -> None:
        if user_id in self._seen_users:
            # Touch — move to MRU position so the eviction policy knows
            # this user is still active.
            self._seen_users.move_to_end(user_id)
            return
        self._seen_users[user_id] = None
        if len(self._seen_users) > self._max_tracked_users:
            # Drop the least-recently-seen user. We deliberately don't
            # decrement the gauge below the cap — we report capacity, not
            # a vanishing count.
            self._seen_users.popitem(last=False)
        self.active_users.set(len(self._seen_users))


def build_metrics_registry() -> MetricsRegistry:
    return MetricsRegistry()
