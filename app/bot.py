from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers import banks, common, history, home, input_flow, preview, settings, start, top
from app.infrastructure.container import AppContainer
from app.infrastructure.telegram_ui import TelegramScreenRenderer
from app.middlewares.db import DbSessionMiddleware
from app.middlewares.error_handler import ErrorHandlerMiddleware
from app.middlewares.logging import LoggingMiddleware


def build_bot(app_container: AppContainer) -> tuple[Bot, Dispatcher, TelegramScreenRenderer]:
    bot = Bot(token=app_container.settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    screen_renderer = TelegramScreenRenderer()

    dispatcher.update.middleware.register(ErrorHandlerMiddleware())
    dispatcher.update.middleware.register(LoggingMiddleware())
    dispatcher.update.middleware.register(DbSessionMiddleware())

    dispatcher.include_router(start.router)
    dispatcher.include_router(home.router)
    dispatcher.include_router(banks.router)
    dispatcher.include_router(input_flow.router)
    dispatcher.include_router(preview.router)
    dispatcher.include_router(top.router)
    dispatcher.include_router(settings.router)
    dispatcher.include_router(history.router)
    dispatcher.include_router(common.router)
    return bot, dispatcher, screen_renderer
