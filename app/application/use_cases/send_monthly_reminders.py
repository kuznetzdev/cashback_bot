from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.application.contracts.ports import ClockPort, ReminderSenderPort, UnitOfWorkPort


class SendMonthlyRemindersUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        sender: ReminderSenderPort,
        clock: ClockPort,
        reminder_hour: int,
        delivery_provider: str | None,
    ) -> None:
        self.uow_factory = uow_factory
        self.sender = sender
        self.clock = clock
        self.reminder_hour = reminder_hour
        self.delivery_provider = delivery_provider

    async def execute(self, now: datetime | None = None) -> int:
        if self.delivery_provider is None:
            return 0
        current = now or self.clock.now()
        if current.day != 1 or current.hour < self.reminder_hour:
            return 0
        period_key = current.strftime("%Y-%m")
        month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        sent_count = 0
        async with self.uow_factory() as uow:
            targets = await uow.identities.list_delivery_targets(provider=self.delivery_provider)
            for target in targets:
                existing = await uow.logs.list_action_since(target.user_id, "reminder_sent", month_start)
                if any((entry.payload or {}).get("period") == period_key for entry in existing):
                    continue
                await self.sender.send_monthly_reminder(target)
                await uow.logs.add(
                    target.user_id,
                    "reminder_sent",
                    {"period": period_key, "provider": target.provider, "destination": target.destination},
                )
                sent_count += 1
            await uow.commit()
        return sent_count
