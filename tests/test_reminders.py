from __future__ import annotations

from datetime import datetime

from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.domain.models import ReminderTarget


class FakeSender:
    def __init__(self) -> None:
        self.sent_to: list[str] = []

    async def send_monthly_reminder(self, target: ReminderTarget) -> None:
        self.sent_to.append(target.destination)


class FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


async def test_monthly_reminder_is_deduplicated_by_log_period(uow_factory) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="User", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="999",
            provider_username="user",
            provider_display_name="User",
        )
        await uow.commit()

    sender = FakeSender()
    now = datetime(2026, 3, 1, 10, 0, 0)
    use_case = SendMonthlyRemindersUseCase(
        uow_factory=uow_factory,
        sender=sender,
        clock=FakeClock(now),
        reminder_hour=10,
    )
    sent_first = await use_case.execute()
    sent_second = await use_case.execute()

    assert sent_first == 1
    assert sent_second == 0
    assert sender.sent_to == ["999"]
