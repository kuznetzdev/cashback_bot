from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.logs import LogsRepository


class HistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.logs = LogsRepository(session)

    async def log(self, user_id: int, action: str, payload: dict[str, Any] | None = None) -> None:
        await self.logs.add(user_id=user_id, action=action, payload=payload)

    async def list_recent(self, user_id: int, limit: int) -> list:
        return await self.logs.list_recent(user_id=user_id, limit=limit)
