"""Notification scheduler abstraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ScheduledNotification:
    user_id: int
    mode: str
    hour: int


class SchedulerService:
    def __init__(self) -> None:
        self._entries: Dict[int, ScheduledNotification] = {}

    def schedule(self, user_id: int, mode: str, hour: int) -> ScheduledNotification:
        entry = ScheduledNotification(user_id=user_id, mode=mode, hour=hour)
        self._entries[user_id] = entry
        return entry

    def cancel(self, user_id: int, mode: Optional[str] = None) -> None:
        entry = self._entries.get(user_id)
        if entry is None:
            return
        if mode is None or entry.mode == mode:
            self._entries.pop(user_id, None)

    def list_all(self) -> List[ScheduledNotification]:
        return list(self._entries.values())
