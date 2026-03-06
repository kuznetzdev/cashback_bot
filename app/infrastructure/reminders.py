from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.constants import REMINDER_ACTION
from app.db.repositories.logs import LogsRepository
from app.db.repositories.users import UsersRepository
from app.infrastructure.container import AppContainer

logger = logging.getLogger(__name__)


class ReminderDispatcher:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.timezone = ZoneInfo(container.settings.app_timezone)

    async def run(self, bot: Bot) -> None:
        while True:
            try:
                await self.dispatch_due_reminders(bot)
            except Exception:
                logger.exception("Reminder loop iteration failed")
            await asyncio.sleep(3600)

    async def dispatch_due_reminders(self, bot: Bot, now: datetime | None = None) -> None:
        now = now or datetime.now(self.timezone)
        if now.day != 1 or now.hour < self.container.settings.reminder_hour:
            return

        period_key = now.strftime("%Y-%m")
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)

        async with self.container.session_factory() as session:
            users_repo = UsersRepository(session)
            logs_repo = LogsRepository(session)
            for user in await users_repo.list_notification_enabled():
                recent = await logs_repo.list_by_action_since(user.id, REMINDER_ACTION, month_start)
                if any((entry.payload_json or {}).get("period") == period_key for entry in recent):
                    continue
                try:
                    await bot.send_message(
                        chat_id=user.telegram_user_id,
                        text=self.container.localizer.gettext(user.language, "reminders.monthly"),
                    )
                except TelegramAPIError:
                    logger.warning("Failed to send reminder to user %s", user.telegram_user_id)
                    continue
                await logs_repo.add(user.id, REMINDER_ACTION, {"period": period_key})
            await session.commit()
