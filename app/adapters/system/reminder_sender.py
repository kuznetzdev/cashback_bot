from __future__ import annotations

from app.application.contracts.ports import ReminderSenderPort
from app.domain.models import ReminderTarget


class NoopReminderSender(ReminderSenderPort):
    async def send_monthly_reminder(self, target: ReminderTarget) -> None:
        _ = target
        return None
