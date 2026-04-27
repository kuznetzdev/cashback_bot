from __future__ import annotations

from app.application.contracts.ports import ReminderSenderPort
from app.domain.models import ReminderTarget


class NoopReminderSender(ReminderSenderPort):
    """No-op implementation used when reminders should not be delivered.

    Examples: web-only deployments without a Telegram bot session, tests
    that exercise the use cases without needing real outbound calls.
    """

    async def send_monthly_reminder(self, target: ReminderTarget) -> None:
        _ = target

    async def send_upcoming_month_reminder(
        self, target: ReminderTarget, *, days_until_next_month: int
    ) -> None:
        _ = target, days_until_next_month

    async def send_stale_data_reminder(self, target: ReminderTarget, *, days_since_last_update: int) -> None:
        _ = target, days_since_last_update
