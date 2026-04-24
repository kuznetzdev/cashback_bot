from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.middleware import (
    LoggingMiddleware,
    ThrottlingMiddleware,
    UserContextMiddleware,
)
from app.bootstrap.correlation import correlation_id_var


def _fake_message(user_id: int = 42, language: str = "ru") -> MagicMock:
    message = MagicMock(spec=[])
    # We don't isinstance()-check Message in our unit tests so a plain MagicMock
    # configured with from_user is enough.
    from_user = MagicMock()
    from_user.id = user_id
    from_user.language_code = language
    message.from_user = from_user
    message.answer = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_user_context_middleware_injects_user_id_and_language() -> None:
    mw = UserContextMiddleware()
    message = _fake_message(user_id=101, language="en")
    captured: dict[str, object] = {}

    async def handler(event, data):
        captured["user_id"] = data.get("tg_user_id")
        captured["language"] = data.get("tg_language_code")
        return "done"

    data: dict[str, object] = {}
    result = await mw(handler, message, data)
    assert result == "done"
    assert captured["user_id"] == 101
    assert captured["language"] == "en"
    # Mutation reaches the handler's data dict.
    assert data["tg_user_id"] == 101


@pytest.mark.asyncio
async def test_throttling_middleware_allows_up_to_capacity() -> None:
    mw = ThrottlingMiddleware(capacity=3, refill_per_second=0.0001)
    message = _fake_message()
    handler = AsyncMock(return_value="ok")
    for _ in range(3):
        result = await mw(handler, message, {})
        assert result == "ok"
    assert handler.call_count == 3


@pytest.mark.asyncio
async def test_throttling_middleware_blocks_when_over_budget() -> None:
    mw = ThrottlingMiddleware(capacity=2, refill_per_second=0.0001)
    message = _fake_message()
    handler = AsyncMock(return_value="ok")
    # Burn the budget.
    await mw(handler, message, {})
    await mw(handler, message, {})
    # Third call should be throttled — handler not invoked, user notified.
    result = await mw(handler, message, {})
    assert result is None
    assert handler.call_count == 2
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_throttling_middleware_lets_unknown_user_through() -> None:
    mw = ThrottlingMiddleware(capacity=1, refill_per_second=0.0001)
    event = MagicMock(spec=[])
    event.from_user = None
    handler = AsyncMock(return_value="ok")
    # Two calls should both succeed because there's no user id to track.
    assert await mw(handler, event, {}) == "ok"
    assert await mw(handler, event, {}) == "ok"
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_logging_middleware_records_call(caplog) -> None:
    mw = LoggingMiddleware()
    message = _fake_message(user_id=7)
    handler = AsyncMock(return_value="ok")

    with caplog.at_level(logging.INFO, logger="telegram.middleware"):
        result = await mw(handler, message, {"handler": MagicMock(callback=handler)})

    assert result == "ok"
    matching = [record for record in caplog.records if record.name == "telegram.middleware"]
    assert matching, "Expected LoggingMiddleware to emit a log record"
    record = matching[0]
    assert getattr(record, "user_id", None) == 7
    assert getattr(record, "status", None) == "ok"


@pytest.mark.asyncio
async def test_logging_middleware_sets_correlation_id_inside_handler() -> None:
    mw = LoggingMiddleware()
    seen: dict[str, str] = {}

    async def handler(event, data):
        seen["cid"] = correlation_id_var.get()
        return "ok"

    await mw(handler, _fake_message(), {})
    assert seen["cid"] != ""


@pytest.mark.asyncio
async def test_logging_middleware_updates_prometheus_metrics() -> None:
    metrics = MagicMock()
    metrics.requests_total = MagicMock()
    metrics.request_duration = MagicMock()
    labels_counter = MagicMock()
    labels_hist = MagicMock()
    metrics.requests_total.labels.return_value = labels_counter
    metrics.request_duration.labels.return_value = labels_hist
    metrics.observe_user = MagicMock()

    mw = LoggingMiddleware(metrics=metrics)
    handler = AsyncMock(return_value="ok")
    await mw(handler, _fake_message(user_id=5), {"handler": MagicMock(callback=handler)})
    labels_counter.inc.assert_called_once()
    labels_hist.observe.assert_called_once()
    metrics.observe_user.assert_called_once_with(5)


@pytest.mark.asyncio
async def test_throttling_blocks_beyond_30_per_minute_window() -> None:
    mw = ThrottlingMiddleware(capacity=30, refill_per_second=0.5)
    message = _fake_message(user_id=1)
    handler = AsyncMock(return_value="ok")
    allowed = 0
    for _ in range(40):
        if await mw(handler, message, {}) == "ok":
            allowed += 1
    assert allowed == 30, f"expected exactly 30 allowed calls, got {allowed}"
