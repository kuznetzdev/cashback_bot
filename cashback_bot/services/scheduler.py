from __future__ import annotations

"""Reminder scheduler for daily/monthly notifications."""
import asyncio
from datetime import datetime, timedelta, time
from typing import Awaitable, Callable

import pytz


class SchedulerService:
    def __init__(self, timezone: str = "UTC") -> None:
        self._timezone = pytz.timezone(timezone)
        self._tasks: list[asyncio.Task] = []

    def schedule_daily(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._tasks.append(asyncio.create_task(self._run_every_day(callback)))

    def schedule_monthly(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._tasks.append(asyncio.create_task(self._run_every_month(callback)))

    async def _run_every_day(self, callback: Callable[[], Awaitable[None]]) -> None:
        while True:
            await self._sleep_until(time(hour=9, minute=0))
            await callback()
            await asyncio.sleep(24 * 3600)

    async def _run_every_month(self, callback: Callable[[], Awaitable[None]]) -> None:
        while True:
            await self._sleep_until(time(hour=9, minute=0))
            now = datetime.now(self._timezone)
            if now.day == 1:
                await callback()
            await asyncio.sleep(24 * 3600)

    async def _sleep_until(self, target: time) -> None:
        now = datetime.now(self._timezone)
        target_dt = self._timezone.localize(datetime.combine(now.date(), target))
        if target_dt < now:
            target_dt += timedelta(days=1)
        await asyncio.sleep((target_dt - now).total_seconds())

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
