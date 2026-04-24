from decimal import Decimal

from app.application.months import current_month_key, shift_month_key
from app.domain.models import CashbackDraftItem


async def test_store_replace_for_bank_behaviour(uow_factory) -> None:
    current_month = current_month_key()
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="User", default_language="ru")
        bank = await uow.banks.create(user.id, "Bank A")
        await uow.cashback.replace_for_bank(
            bank.id,
            current_month,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5"),
                    source_type="manual",
                )
            ],
        )
        await uow.cashback.replace_for_bank(
            bank.id,
            current_month,
            [
                CashbackDraftItem(
                    raw_category="Аптеки",
                    normalized_category="pharmacy",
                    percent=Decimal("3"),
                    source_type="manual",
                )
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        items = await uow.cashback.list_for_bank(bank.id, current_month)
    assert len(items) == 1
    assert items[0].normalized_category == "pharmacy"


async def test_store_keeps_month_snapshots_separately(uow_factory) -> None:
    current_month = current_month_key()
    next_month = shift_month_key(current_month, 1)
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="User", default_language="ru")
        bank = await uow.banks.create(user.id, "Bank A")
        await uow.cashback.replace_for_bank(
            bank.id,
            current_month,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5"),
                    source_type="manual",
                )
            ],
        )
        await uow.cashback.replace_for_bank(
            bank.id,
            next_month,
            [
                CashbackDraftItem(
                    raw_category="Рестораны",
                    normalized_category="restaurants",
                    percent=Decimal("7"),
                    source_type="manual",
                )
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        current_items = await uow.cashback.list_for_bank(bank.id, current_month)
        next_items = await uow.cashback.list_for_bank(bank.id, next_month)
        months = await uow.cashback.list_months_for_bank(bank.id)

    assert [item.normalized_category for item in current_items] == ["fuel"]
    assert [item.normalized_category for item in next_items] == ["restaurants"]
    assert months == [current_month, next_month]
