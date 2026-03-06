from decimal import Decimal

import pytest

from app.schemas.cashback_item import DraftCashbackItem


@pytest.mark.asyncio
async def test_catalog_save_replace_and_delete_bank(app_container, session, db_user) -> None:
    items = [
        DraftCashbackItem(
            raw_category="АЗС",
            normalized_category="fuel",
            percent=Decimal("5"),
            source_type="manual",
        )
    ]
    bank = await app_container.catalog_service.save_bank(
        session,
        db_user,
        bank_name="T-Bank Black",
        items=items,
        source_type="manual",
    )

    details = await app_container.catalog_service.get_bank_details(session, db_user, bank.id)
    assert details.bank_name == "T-Bank Black"
    assert len(details.items) == 1

    updated_items = [
        DraftCashbackItem(
            raw_category="Рестораны",
            normalized_category="restaurants",
            percent=Decimal("7"),
            source_type="manual",
        )
    ]
    await app_container.catalog_service.save_bank(
        session,
        db_user,
        bank_name="T-Bank Black",
        items=updated_items,
        source_type="manual",
        bank_id=bank.id,
    )

    updated = await app_container.catalog_service.get_bank_details(session, db_user, bank.id)
    assert len(updated.items) == 1
    assert updated.items[0].normalized_category == "restaurants"

    await app_container.catalog_service.delete_bank(session, db_user, bank.id)
    banks = await app_container.catalog_service.list_banks(session, db_user)
    assert banks == []
