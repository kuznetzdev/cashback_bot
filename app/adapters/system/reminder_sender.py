from __future__ import annotations

from app.application.contracts.ports import ReminderSenderPort
from app.domain.models import UserProfile


class NoopReminderSender(ReminderSenderPort):
    async def send_monthly_reminder(self, user: UserProfile) -> None:
        _ = user
        return None
