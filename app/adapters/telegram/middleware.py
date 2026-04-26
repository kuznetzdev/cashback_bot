"""Aiogram middleware used by the telegram router.

Three responsibilities kept in separate classes so routing remains pluggable
and each concern can be unit-tested in isolation:

* :class:`LoggingMiddleware` — emits a log record per update with handler name
  and latency. Also sets a short correlation id (``correlation_id_var``) so the
  handler's structlog output can be traced back to the originating update.
* :class:`ThrottlingMiddleware` — global per-user message rate limit (defaults
  to 30 msg/min with burst of 30). Distinct from the photo-specific bucket in
  :mod:`app.adapters.telegram.router` which still guards OCR cost.
* :class:`UserContextMiddleware` — extracts Telegram user id + language code
  from the update and puts them in the handler ``data`` dict so downstream code
  doesn't need to re-derive them from different update types.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject, Update

from app.adapters.rate_limit import TokenBucketRateLimiter
from app.bootstrap.correlation import correlation_id_var

logger = logging.getLogger("telegram.middleware")


def _extract_user_id(event: TelegramObject) -> int | None:
    """Best-effort user-id extraction across Message/CallbackQuery/InlineQuery
    and raw Update envelopes. Returns None for service updates we don't care
    to throttle (bot joined chat, etc.)."""
    candidates: list[object] = []
    if isinstance(event, Update):
        if event.message is not None:
            candidates.append(event.message)
        if event.callback_query is not None:
            candidates.append(event.callback_query)
        if event.inline_query is not None:
            candidates.append(event.inline_query)
    else:
        candidates.append(event)
    for candidate in candidates:
        from_user = getattr(candidate, "from_user", None)
        if from_user is not None and getattr(from_user, "id", None) is not None:
            try:
                return int(from_user.id)
            except (TypeError, ValueError):
                return None
    return None


def _extract_language_code(event: TelegramObject) -> str | None:
    candidates: list[object] = []
    if isinstance(event, Update):
        for field in (event.message, event.callback_query, event.inline_query):
            if field is not None:
                candidates.append(field)
    else:
        candidates.append(event)
    for candidate in candidates:
        from_user = getattr(candidate, "from_user", None)
        if from_user is not None:
            code = getattr(from_user, "language_code", None)
            if code:
                return str(code)
    return None


def _describe_update(event: TelegramObject) -> str:
    if isinstance(event, Message):
        return "message"
    if isinstance(event, CallbackQuery):
        return "callback_query"
    if isinstance(event, InlineQuery):
        return "inline_query"
    if isinstance(event, Update):
        if event.message is not None:
            return "update.message"
        if event.callback_query is not None:
            return "update.callback_query"
        if event.inline_query is not None:
            return "update.inline_query"
        return "update"
    return event.__class__.__name__.lower()


class LoggingMiddleware(BaseMiddleware):
    """Logs one line per update with handler + latency. Also sets a
    per-update correlation id so structlog records emitted inside handlers
    carry the same id for easy tracing."""

    def __init__(self, metrics: Any | None = None) -> None:
        self._metrics = metrics

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        correlation_id = str(uuid.uuid4())[:8]
        token = correlation_id_var.set(correlation_id)
        user_id = _extract_user_id(event)
        update_kind = _describe_update(event)
        handler_name = _resolve_handler_name(data)
        started_monotonic = time.monotonic()
        status = "ok"
        try:
            result = await handler(event, data)
            return result
        except Exception:
            status = "error"
            raise
        finally:
            elapsed_ms = (time.monotonic() - started_monotonic) * 1000.0
            logger.info(
                "telegram_update",
                extra={
                    "correlation_id": correlation_id,
                    "user_id": user_id,
                    "update_type": update_kind,
                    "handler": handler_name,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "status": status,
                },
            )
            if self._metrics is not None:
                try:
                    self._metrics.requests_total.labels(handler=handler_name, status=status).inc()
                    self._metrics.request_duration.labels(handler=handler_name).observe(elapsed_ms / 1000.0)
                    if user_id is not None:
                        self._metrics.observe_user(user_id)
                except Exception:  # pragma: no cover - metrics must never crash a handler
                    pass
            correlation_id_var.reset(token)


def _resolve_handler_name(data: dict[str, Any]) -> str:
    handler_obj = data.get("handler")
    if handler_obj is not None:
        inner = getattr(handler_obj, "callback", None) or handler_obj
        name = getattr(inner, "__name__", None)
        if name:
            return str(name)
    return "unknown"


class ThrottlingMiddleware(BaseMiddleware):
    """Global per-user throttle. Defaults to 30 msg/minute (burst 30, refill
    0.5 msg/s). Callback queries and inline queries are throttled too so a
    malicious user can't spin the handler by holding a mouse button on a
    keyboard; we use a single bucket per user id."""

    def __init__(
        self,
        *,
        capacity: int = 30,
        refill_per_second: float = 0.5,
        notify_text: str = "⏳ Подождите немного — слишком много запросов.",
    ) -> None:
        self._limiter = TokenBucketRateLimiter(
            capacity=capacity,
            refill_per_second=refill_per_second,
        )
        self._notify_text = notify_text

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event)
        if user_id is None:
            # No user id → service update, let it through; we can't attribute it.
            return await handler(event, data)
        if self._limiter.allow(user_id):
            return await handler(event, data)
        # Over budget — let the user know briefly and drop the handler call.
        # Duck-type on `.answer`: covers Message (text reply) and CallbackQuery
        # (toast). Other update types without `.answer` silently drop.
        notify = getattr(event, "answer", None)
        if callable(notify):
            try:
                if isinstance(event, CallbackQuery):
                    await notify(self._notify_text, show_alert=False)
                else:
                    await notify(self._notify_text)
            except Exception:  # pragma: no cover - prefer silent drop over retry loop
                pass
        return None


class UserContextMiddleware(BaseMiddleware):
    """Populates ``data['tg_user_id']`` and ``data['tg_language_code']`` so
    handlers don't need to branch on update type to extract them."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["tg_user_id"] = _extract_user_id(event)
        data["tg_language_code"] = _extract_language_code(event)
        return await handler(event, data)
