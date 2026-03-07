from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.application.contracts.ports import ClockPort


class SystemClock(ClockPort):
    def __init__(self, timezone: str) -> None:
        self.timezone = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self.timezone)
