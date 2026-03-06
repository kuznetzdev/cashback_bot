from __future__ import annotations

from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.users import UsersRepository
from app.infrastructure.container import AppContainer


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        app_container: AppContainer = data["app_container"]
        async with app_container.session_factory() as session:
            data["session"] = session
            from_user = getattr(event, "from_user", None)
            if from_user is not None:
                db_user = await UsersRepository(session).upsert(
                    telegram_user_id=from_user.id,
                    username=from_user.username,
                    full_name=from_user.full_name,
                    default_language=app_container.settings.lang_default,
                )
                data["db_user"] = db_user
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result
