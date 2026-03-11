from decimal import Decimal

from app.domain.models import CashbackDraftItem


async def test_store_replace_for_bank_behaviour(uow_factory) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="User", default_language="ru")
        bank = await uow.banks.create(user.id, "Bank A")
        await uow.cashback.replace_for_bank(
            bank.id,
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
        items = await uow.cashback.list_for_bank(bank.id)
    assert len(items) == 1
    assert items[0].normalized_category == "pharmacy"
