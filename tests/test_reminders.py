from __future__ import annotations

from datetime import datetime

from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.domain.models import UserProfile


class FakeSender:
    def __init__(self) -> None:
        self.sent_to: list[int] = []

    async def send_monthly_reminder(self, user: UserProfile) -> None:
        self.sent_to.append(user.external_user_id)


class FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


async def test_monthly_reminder_is_deduplicated_by_log_period(uow_factory) -> None:
    async with uow_factory() as uow:
        user = await uow.users.upsert(
            external_user_id=999,
            username="user",
            full_name="User",
            default_language="ru",
        )
        user.notifications_enabled = True
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
    assert sender.sent_to == [999]
