from __future__ import annotations

from aiogram import Bot

from app.application.contracts.ports import ReminderSenderPort
from app.domain.models import ReminderTarget
from app.i18n.localizer import Localizer


class TelegramReminderSender(ReminderSenderPort):
    def __init__(self, bot: Bot, localizer: Localizer) -> None:
        self.bot = bot
        self.localizer = localizer

    async def send_monthly_reminder(self, target: ReminderTarget) -> None:
        text = self.localizer.t("messages.reminder_monthly", target.language)
        await self.bot.send_message(chat_id=int(target.destination), text=text)
