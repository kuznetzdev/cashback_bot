from __future__ import annotations

import logging

from aiogram import BaseMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        from_user = getattr(event, "from_user", None)
        logger.info("Update %s from user=%s", type(event).__name__, getattr(from_user, "id", None))
        return await handler(event, data)
