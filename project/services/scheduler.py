"""Async reminder scheduling."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable

import pytz

LOGGER = logging.getLogger(__name__)

ReminderCallback = Callable[[], Awaitable[None]]


class ReminderScheduler:
    """Periodic scheduler that delegates notification checks."""

    def __init__(self, timezone: str = "UTC", interval_minutes: int = 60) -> None:
        self._timezone = pytz.timezone(timezone)
        self._interval = max(1, interval_minutes)
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def start(self, callback: ReminderCallback) -> None:
        if self._task is not None:
            LOGGER.debug("Scheduler already started")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(callback))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopped.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            LOGGER.debug("Scheduler task cancelled")
        finally:
            self._task = None

    async def _run(self, callback: ReminderCallback) -> None:
        while not self._stopped.is_set():
            try:
                await callback()
            except Exception:  # pragma: no cover - defensive
                LOGGER.exception("Reminder callback failed")
            try:
                await asyncio.wait_for(
                    self._stopped.wait(), timeout=self._interval * 60
                )
            except asyncio.TimeoutError:
                continue

