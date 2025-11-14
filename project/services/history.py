"""History and journal service."""
from __future__ import annotations

from typing import Any, List

from .db import AsyncDatabase


class HistoryService:
    """Store and fetch user activity entries."""

    def __init__(self, db: AsyncDatabase, max_records: int) -> None:
        self._db = db
        self._max_records = max_records

    async def record(self, user_id: int, action: str, metadata: dict[str, Any] | None = None) -> None:
        await self._db.log_activity(user_id, action, metadata)

    async def list(self, user_id: int) -> List[dict[str, Any]]:
        return await self._db.list_activity(user_id, self._max_records)

    async def clear(self, user_id: int) -> None:
        await self._db.clear_activity(user_id)

