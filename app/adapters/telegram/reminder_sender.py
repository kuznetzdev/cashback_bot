from __future__ import annotations

from aiogram import Bot

from app.application.contracts.ports import ReminderSenderPort
from app.domain.models import ReminderTarget
from app.i18n.localizer import Localizer


class TelegramReminderSender(ReminderSenderPort):
    """Renders reminder text via :class:`Localizer` and posts it to the
    target chat. Three reminder flavours share the same delivery path so
    transport-level concerns (rate limits, blocked-bot 403s, retries)
    only need handling once."""

    def __init__(self, bot: Bot, localizer: Localizer) -> None:
        self.bot = bot
        self.localizer = localizer

    async def send_monthly_reminder(self, target: ReminderTarget) -> None:
        text = self.localizer.t("messages.reminder_monthly", target.language)
        await self.bot.send_message(chat_id=int(target.destination), text=text)

    async def send_upcoming_month_reminder(
        self, target: ReminderTarget, *, days_until_next_month: int
    ) -> None:
        text = self.localizer.t(
            "messages.reminder_upcoming_month",
            target.language,
            {"days": days_until_next_month},
        )
        await self.bot.send_message(chat_id=int(target.destination), text=text)

    async def send_stale_data_reminder(self, target: ReminderTarget, *, days_since_last_update: int) -> None:
        text = self.localizer.t(
            "messages.reminder_stale_data",
            target.language,
            {"days": days_since_last_update},
        )
        await self.bot.send_message(chat_id=int(target.destination), text=text)
