from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.application.use_cases.send_pre_month_reminders import (
    SendPreMonthRemindersUseCase,
)
from app.application.use_cases.send_stale_data_reminders import (
    SendStaleDataRemindersUseCase,
)
from app.domain.models import CashbackDraftItem


class _FixedClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


class _RecordingSender:
    """In-memory ``ReminderSenderPort`` that just collects calls so tests
    can assert on exactly what would have gone over the wire."""

    def __init__(self) -> None:
        self.monthly: list[object] = []
        self.upcoming: list[tuple[object, int]] = []
        self.stale: list[tuple[object, int]] = []

    async def send_monthly_reminder(self, target):  # type: ignore[no-untyped-def]
        self.monthly.append(target)

    async def send_upcoming_month_reminder(self, target, *, days_until_next_month):  # type: ignore[no-untyped-def]
        self.upcoming.append((target, days_until_next_month))

    async def send_stale_data_reminder(self, target, *, days_since_last_update):  # type: ignore[no-untyped-def]
        self.stale.append((target, days_since_last_update))


async def _seed_user_with_bank(uow_factory, *, telegram_id: str = "111") -> int:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id=telegram_id,
            provider_username=None,
            provider_display_name=None,
        )
        bank = await uow.banks.create(user.id, "Tinkoff")
        await uow.cashback.replace_for_bank(
            bank.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5.00"),
                    source_type="manual",
                ),
            ],
        )
        await uow.commit()
    return user.id


# --- Pre-month reminder ----------------------------------------------------


@pytest.mark.asyncio
async def test_pre_month_reminder_fires_three_days_before_month_end(uow_factory) -> None:
    await _seed_user_with_bank(uow_factory)
    clock = _FixedClock(datetime(2026, 4, 28, 11, 0))  # 3 days left
    sender = _RecordingSender()
    use_case = SendPreMonthRemindersUseCase(uow_factory, sender, clock, window_days=3, reminder_hour=10)
    sent = await use_case.execute()
    assert sent == 1
    assert len(sender.upcoming) == 1
    target, days_left = sender.upcoming[0]
    assert days_left == 3
    assert target.provider == "telegram"


@pytest.mark.asyncio
async def test_pre_month_reminder_skips_outside_window(uow_factory) -> None:
    await _seed_user_with_bank(uow_factory)
    clock = _FixedClock(datetime(2026, 4, 10, 11, 0))  # mid-month
    sender = _RecordingSender()
    use_case = SendPreMonthRemindersUseCase(uow_factory, sender, clock, window_days=3)
    assert await use_case.execute() == 0
    assert sender.upcoming == []


@pytest.mark.asyncio
async def test_pre_month_reminder_skips_users_without_banks(uow_factory) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="No banks", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="222",
            provider_username=None,
            provider_display_name=None,
        )
        await uow.commit()
    clock = _FixedClock(datetime(2026, 4, 30, 11, 0))  # last day of month
    sender = _RecordingSender()
    use_case = SendPreMonthRemindersUseCase(uow_factory, sender, clock)
    assert await use_case.execute() == 0
    assert sender.upcoming == []


@pytest.mark.asyncio
async def test_pre_month_reminder_dedupes_within_same_period(uow_factory) -> None:
    await _seed_user_with_bank(uow_factory)
    clock = _FixedClock(datetime(2026, 4, 30, 11, 0))
    sender = _RecordingSender()
    use_case = SendPreMonthRemindersUseCase(uow_factory, sender, clock, window_days=3)
    first = await use_case.execute()
    second = await use_case.execute()
    assert first == 1
    assert second == 0  # already sent for the upcoming May period


@pytest.mark.asyncio
async def test_pre_month_reminder_respects_reminder_hour(uow_factory) -> None:
    await _seed_user_with_bank(uow_factory)
    clock = _FixedClock(datetime(2026, 4, 28, 9, 0))  # before 10:00 cut-off
    sender = _RecordingSender()
    use_case = SendPreMonthRemindersUseCase(uow_factory, sender, clock, window_days=3, reminder_hour=10)
    assert await use_case.execute() == 0
    assert sender.upcoming == []


@pytest.mark.asyncio
async def test_pre_month_reminder_handles_december_rollover(uow_factory) -> None:
    await _seed_user_with_bank(uow_factory)
    clock = _FixedClock(datetime(2026, 12, 30, 11, 0))  # 2 days left → into Jan 2027
    sender = _RecordingSender()
    use_case = SendPreMonthRemindersUseCase(uow_factory, sender, clock, window_days=3)
    assert await use_case.execute() == 1


# --- Stale-data reminder ---------------------------------------------------


@pytest.mark.asyncio
async def test_stale_data_reminder_fires_after_threshold(uow_factory, monkeypatch) -> None:
    user_id = await _seed_user_with_bank(uow_factory)
    # Backdate the bank's freshness marker by 20 days.
    async with uow_factory() as uow:
        for bank in await uow.banks.list_for_user(user_id):
            uow.banks.store.bank_updated_at[bank.id] = datetime.now() - timedelta(days=20)

    clock = _FixedClock(datetime.now().replace(hour=11, minute=0, second=0, microsecond=0))
    sender = _RecordingSender()
    use_case = SendStaleDataRemindersUseCase(uow_factory, sender, clock, threshold_days=14)
    assert await use_case.execute() == 1
    assert len(sender.stale) == 1


@pytest.mark.asyncio
async def test_stale_data_reminder_does_not_fire_under_threshold(uow_factory) -> None:
    user_id = await _seed_user_with_bank(uow_factory)
    # Recent update — well under the 14-day threshold.
    async with uow_factory() as uow:
        for bank in await uow.banks.list_for_user(user_id):
            uow.banks.store.bank_updated_at[bank.id] = datetime.now() - timedelta(days=2)
    clock = _FixedClock(datetime.now().replace(hour=11, minute=0, second=0, microsecond=0))
    sender = _RecordingSender()
    use_case = SendStaleDataRemindersUseCase(uow_factory, sender, clock, threshold_days=14)
    assert await use_case.execute() == 0


@pytest.mark.asyncio
async def test_stale_data_reminder_dedupes_within_month(uow_factory) -> None:
    user_id = await _seed_user_with_bank(uow_factory)
    async with uow_factory() as uow:
        for bank in await uow.banks.list_for_user(user_id):
            uow.banks.store.bank_updated_at[bank.id] = datetime.now() - timedelta(days=20)
    clock = _FixedClock(datetime.now().replace(hour=11, minute=0, second=0, microsecond=0))
    sender = _RecordingSender()
    use_case = SendStaleDataRemindersUseCase(uow_factory, sender, clock, threshold_days=14)
    assert await use_case.execute() == 1
    assert await use_case.execute() == 0  # second tick is deduped


@pytest.mark.asyncio
async def test_stale_data_reminder_skips_users_without_banks(uow_factory) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="No banks", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="333",
            provider_username=None,
            provider_display_name=None,
        )
        await uow.commit()
    clock = _FixedClock(datetime.now().replace(hour=11, minute=0, second=0, microsecond=0))
    sender = _RecordingSender()
    use_case = SendStaleDataRemindersUseCase(uow_factory, sender, clock)
    assert await use_case.execute() == 0


@pytest.mark.asyncio
async def test_stale_data_reminder_swallows_per_user_send_failures(uow_factory) -> None:
    user_id = await _seed_user_with_bank(uow_factory)
    async with uow_factory() as uow:
        for bank in await uow.banks.list_for_user(user_id):
            uow.banks.store.bank_updated_at[bank.id] = datetime.now() - timedelta(days=20)

    class _FlakeySender(_RecordingSender):
        async def send_stale_data_reminder(self, target, *, days_since_last_update):  # type: ignore[no-untyped-def]
            raise RuntimeError("user blocked the bot")

    clock = _FixedClock(datetime.now().replace(hour=11, minute=0, second=0, microsecond=0))
    sender = _FlakeySender()
    use_case = SendStaleDataRemindersUseCase(uow_factory, sender, clock, threshold_days=14)
    # Delivery raised; sent_count stays 0 but the loop didn't propagate the
    # exception — that's the documented behaviour.
    assert await use_case.execute() == 0


@pytest.mark.asyncio
async def test_stale_data_reminder_rejects_invalid_construction() -> None:
    class _StubFactory:
        pass

    sender = _RecordingSender()
    clock = _FixedClock(datetime.now())
    with pytest.raises(ValueError):
        SendStaleDataRemindersUseCase(_StubFactory(), sender, clock, threshold_days=0)
    with pytest.raises(ValueError):
        SendStaleDataRemindersUseCase(_StubFactory(), sender, clock, reminder_hour=24)
