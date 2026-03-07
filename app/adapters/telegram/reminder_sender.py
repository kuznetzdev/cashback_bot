from __future__ import annotations

from aiogram import Bot

from app.adapters.telegram.localizer import Localizer
from app.application.contracts.ports import ReminderSenderPort
from app.domain.models import UserProfile


class TelegramReminderSender(ReminderSenderPort):
    def __init__(self, bot: Bot, localizer: Localizer) -> None:
        self.bot = bot
        self.localizer = localizer

    async def send_monthly_reminder(self, user: UserProfile) -> None:
        text = self.localizer.t("messages.reminder_monthly", user.language)
        await self.bot.send_message(chat_id=user.external_user_id, text=text)
