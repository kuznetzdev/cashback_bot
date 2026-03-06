from __future__ import annotations

import asyncio
import contextlib

from aiogram.types import BotCommand

from app.bot import build_bot
from app.config import get_settings
from app.core.logger import configure_logging
from app.db.session import create_session_factory
from app.infrastructure.container import build_container
from app.infrastructure.reminders import ReminderDispatcher


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine, session_factory = create_session_factory(settings.sqlalchemy_database_uri)
    app_container = build_container(settings, session_factory)
    bot, dispatcher, screen_renderer = build_bot(app_container)
    reminder_dispatcher = ReminderDispatcher(app_container)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open home"),
            BotCommand(command="add", description="Add bank"),
            BotCommand(command="top", description="Show rankings"),
            BotCommand(command="settings", description="Open settings"),
            BotCommand(command="history", description="Show history"),
            BotCommand(command="help", description="Show help"),
        ]
    )

    reminder_task = asyncio.create_task(reminder_dispatcher.run(bot))
    try:
        await dispatcher.start_polling(
            bot,
            app_container=app_container,
            screen_renderer=screen_renderer,
        )
    finally:
        reminder_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminder_task
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
