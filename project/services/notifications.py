"""Notification handling helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from telegram.ext import Application

from ..config import BotConfig
from ..i18n import Translator
from .db import AsyncDatabase, NotificationSettings


class NotificationService:
    """Encapsulate logic for extended notification schedules."""

    def __init__(self, db: AsyncDatabase, translator: Translator, config: BotConfig) -> None:
        self._db = db
        self._translator = translator
        self._config = config

    async def get_settings(self, user_id: int) -> NotificationSettings:
        return await self._db.get_notification_settings(user_id)

    async def update_settings(
        self,
        user_id: int,
        *,
        monthly: bool,
        warning: bool,
        critical: bool,
    ) -> None:
        await self._db.update_notification_settings(user_id, monthly, warning, critical)

    async def render_settings(self, user_id: int, locale: str) -> str:
        settings = await self.get_settings(user_id)
        lines = [self._translate("notifications_header", locale)]
        lines.append(self._format_toggle("notifications_monthly", settings.monthly_enabled, locale))
        lines.append(self._format_toggle("notifications_warning", settings.inactivity_warning_enabled, locale))
        lines.append(self._format_toggle("notifications_critical", settings.inactivity_critical_enabled, locale))
        return "\n".join(lines)

    def _format_toggle(self, key: str, enabled: bool, locale: str) -> str:
        state = self._translate("notifications_on", locale) if enabled else self._translate("notifications_off", locale)
        return f"• {self._translate(key, locale)} — {state}"

    def _translate(self, key: str, locale: str) -> str:
        return self._translator.translate(key, locale)

    async def process_notifications(self, application: Application) -> None:
        now = datetime.now(timezone.utc)
        users = await self._db.list_users()
        for user in users:
            user_id = int(user["id"])
            settings = await self.get_settings(user_id)
            locale = user.get("language", self._translator.default_locale)
            if settings.monthly_enabled and self._should_send_monthly(settings, now):
                await self._send(application, user["telegram_id"], "reminder_monthly", locale)
                await self._db.mark_notification_sent(user_id, "monthly")
            if settings.inactivity_warning_enabled and self._should_send_warning(user, settings, now):
                await self._send(application, user["telegram_id"], "reminder_warning", locale)
                await self._db.mark_notification_sent(user_id, "warning")
            if settings.inactivity_critical_enabled and self._should_send_critical(user, settings, now):
                await self._send(application, user["telegram_id"], "reminder_critical", locale)
                await self._db.mark_notification_sent(user_id, "critical")

    async def _send(self, application: Application, chat_id: int, key: str, locale: str) -> None:
        await application.bot.send_message(chat_id=chat_id, text=self._translate(key, locale))

    def _should_send_monthly(self, settings: NotificationSettings, now: datetime) -> bool:
        if now.day != 1:
            return False
        if settings.last_monthly_sent:
            last = self._parse_timestamp(settings.last_monthly_sent)
            return last.date() != now.date()
        return True

    def _should_send_warning(self, user_row: dict[str, Any], settings: NotificationSettings, now: datetime) -> bool:
        last_update = self._parse_timestamp(user_row.get("last_bank_update"))
        if last_update is None:
            return False
        delta = now - last_update
        if delta < timedelta(days=self._config.inactivity_warning_days):
            return False
        if settings.last_warning_sent:
            last = self._parse_timestamp(settings.last_warning_sent)
            if last and (now - last) < timedelta(days=5):
                return False
        return True

    def _should_send_critical(self, user_row: dict[str, Any], settings: NotificationSettings, now: datetime) -> bool:
        last_activity = self._parse_timestamp(user_row.get("last_activity"))
        if last_activity is None:
            return False
        if now - last_activity < timedelta(days=self._config.inactivity_critical_days):
            return False
        if settings.last_critical_sent:
            last = self._parse_timestamp(settings.last_critical_sent)
            if last and (now - last) < timedelta(days=10):
                return False
        return True

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

