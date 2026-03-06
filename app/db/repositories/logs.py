from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import UserLog


class LogsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user_id: int, action: str, payload: dict[str, Any] | None = None) -> UserLog:
        entry = UserLog(
            user_id=user_id,
            action=action,
            payload_json=payload,
            created_at=utcnow(),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_recent(self, user_id: int, limit: int) -> list[UserLog]:
        result = await self.session.execute(
            select(UserLog)
            .where(UserLog.user_id == user_id)
            .order_by(desc(UserLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_action_since(self, user_id: int, action: str, since: datetime) -> list[UserLog]:
        result = await self.session.execute(
            select(UserLog)
            .where(
                UserLog.user_id == user_id,
                UserLog.action == action,
                UserLog.created_at >= since,
            )
            .order_by(desc(UserLog.created_at))
        )
        return list(result.scalars().all())
