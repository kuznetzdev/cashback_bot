from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UsersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        full_name: str | None,
        default_language: str,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                full_name=full_name,
                language=default_language,
                notifications_enabled=True,
            )
            self.session.add(user)
            await self.session.flush()
            return user

        user.username = username
        user.full_name = full_name
        await self.session.flush()
        return user

    async def list_notification_enabled(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.notifications_enabled.is_(True))
        )
        return list(result.scalars().all())
