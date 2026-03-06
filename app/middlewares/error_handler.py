from __future__ import annotations

import logging
from contextlib import suppress

from aiogram import BaseMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, DatabaseOperationError
from app.db.models import User
from app.services.history import HistoryService

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except SQLAlchemyError as error:
            logger.exception("Database error during update processing")
            await self._handle_error(event, data, DatabaseOperationError())
            return None
        except AppError as error:
            logger.warning("Application error: %s", error.message_key)
            await self._handle_error(event, data, error)
            return None
        except Exception as error:
            logger.exception("Unexpected error during update processing")
            await self._handle_error(event, data, AppError("errors.unexpected", log_action="unexpected_error"))
            return None

    async def _handle_error(self, event, data, error: AppError) -> None:
        session: AsyncSession | None = data.get("session")
        db_user: User | None = data.get("db_user")
        app_container = data["app_container"]
        screen_renderer = data["screen_renderer"]
        if session is not None:
            with suppress(Exception):
                await session.rollback()
        if error.log_action and db_user is not None:
            async with app_container.session_factory() as log_session:
                await HistoryService(log_session).log(db_user.id, error.log_action, error.payload)
                await log_session.commit()

        language = db_user.language if db_user is not None else app_container.settings.lang_default
        await screen_renderer.notify_error(event, app_container.localizer.gettext(language, error.message_key))
