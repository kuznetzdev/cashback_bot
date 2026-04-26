"""Shared Prometheus metrics registry.

Historically the metrics lived inside ``app/adapters/web/app.py`` — fine
while only the LoggingMiddleware fed them. As soon as other layers (OCR
adapters, scheduler) want to record counts, a shared module makes more
sense: all counters/histograms live here and the web app just renders
the same registry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

logger = logging.getLogger(__name__)


class MetricsRegistry:
    """Typed wrapper around the Prometheus collector registry.

    Instantiate once at process start (in ``runtime.run_app``), share the
    instance with every adapter that needs to record samples, and expose
    ``.registry`` to the Prometheus exposition endpoint.
    """

    def __init__(self) -> None:
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
            "Unique users seen in the current process window",
            registry=self.registry,
        )
        self._seen_users: set[int] = set()

    def observe_user(self, user_id: int) -> None:
        if user_id in self._seen_users:
            return
        self._seen_users.add(user_id)
        self.active_users.set(len(self._seen_users))


def build_metrics_registry() -> MetricsRegistry:
    return MetricsRegistry()
