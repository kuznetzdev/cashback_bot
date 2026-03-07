from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class ReminderLoop:
    def __init__(self, send_once: Callable[[], Awaitable[int]], *, interval_seconds: int = 3600) -> None:
        self.send_once = send_once
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="monthly-reminder-loop")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        await self._task
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                sent = await self.send_once()
                if sent > 0:
                    logger.info("Monthly reminders sent: %s", sent)
            except RuntimeError as error:
                logger.exception("Reminder loop runtime error: %s", error)
            except OSError as error:
                logger.exception("Reminder loop I/O error: %s", error)
            except Exception as error:
                logger.exception("Reminder loop unhandled error: %s", error)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue
