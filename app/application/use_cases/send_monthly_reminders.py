from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.application.contracts.ports import ClockPort, ReminderSenderPort, UnitOfWorkPort
from app.domain.models import UserProfile


class SendMonthlyRemindersUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        sender: ReminderSenderPort,
        clock: ClockPort,
        reminder_hour: int,
    ) -> None:
        self.uow_factory = uow_factory
        self.sender = sender
        self.clock = clock
        self.reminder_hour = reminder_hour

    async def execute(self, now: datetime | None = None) -> int:
        current = now or self.clock.now()
        if current.day != 1 or current.hour < self.reminder_hour:
            return 0
        period_key = current.strftime("%Y-%m")
        month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        sent_count = 0
        async with self.uow_factory() as uow:
            users: list[UserProfile] = await uow.users.list_notification_enabled()
            for user in users:
                existing = await uow.logs.list_action_since(user.id, "reminder_sent", month_start)
                if any((entry.payload or {}).get("period") == period_key for entry in existing):
                    continue
                await self.sender.send_monthly_reminder(user)
                await uow.logs.add(user.id, "reminder_sent", {"period": period_key})
                sent_count += 1
            await uow.commit()
        return sent_count
