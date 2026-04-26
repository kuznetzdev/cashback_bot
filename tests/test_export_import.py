from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from decimal import Decimal

import pytest

from app.application.use_cases.export_user_data import SCHEMA_VERSION, ExportUserDataUseCase
from app.application.use_cases.import_user_data import ImportUserDataUseCase
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem


@pytest.mark.asyncio
async def test_export_returns_empty_envelope_for_unknown_user(uow_factory) -> None:
    use_case = ExportUserDataUseCase(uow_factory)
    export = await use_case.execute(user_id=9999)
    assert export.schema_version == SCHEMA_VERSION
    assert export.banks == []
    # Empty user envelope is OK — caller can still tell which user_id they asked about.
    assert export.user["id"] == 9999


@pytest.mark.asyncio
async def test_export_serialises_user_banks_and_items(uow_factory, store) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="Aleksandr", default_language="ru")
        bank = await uow.banks.create(user.id, "Tinkoff")
        await uow.cashback.replace_for_bank(
            bank.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5.00"),
                    source_type="manual",
                    monthly_limit=Decimal("3000.00"),
                ),
            ],
        )
        await uow.commit()

    use_case = ExportUserDataUseCase(
        uow_factory,
        clock=lambda: datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
    )
    export = await use_case.execute(user_id=user.id)
    payload = export.to_dict()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["exported_at"] == "2026-04-25T12:00:00Z"
    assert payload["user"]["id"] == user.id
    assert payload["user"]["display_name"] == "Aleksandr"
    assert len(payload["banks"]) == 1
    bank_payload = payload["banks"][0]
    assert bank_payload["bank_name"] == "Tinkoff"
    assert len(bank_payload["items"]) == 1
    item_payload = bank_payload["items"][0]
    assert item_payload["raw_category"] == "АЗС"
    assert item_payload["normalized_category"] == "fuel"
    assert item_payload["percent"] == "5.00"
    assert item_payload["monthly_limit"] == "3000.00"
    # Whole tree must be JSON-serialisable.
    json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_import_replaces_existing_banks(uow_factory, store) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        existing_bank = await uow.banks.create(user.id, "OldBank")
        await uow.cashback.replace_for_bank(
            existing_bank.id,
            [
                CashbackDraftItem(
                    raw_category="Стоп",
                    normalized_category="other",
                    percent=Decimal("1.00"),
                    source_type="manual",
                ),
            ],
        )
        await uow.commit()

    payload = {
        "schema_version": 1,
        "user": {"id": user.id, "display_name": "U"},
        "banks": [
            {
                "bank_name": "Tinkoff",
                "items": [
                    {
                        "raw_category": "АЗС",
                        "normalized_category": "fuel",
                        "percent": "5",
                        "source_type": "imported",
                        "monthly_limit": "3000",
                    },
                    {
                        "raw_category": "Рестораны",
                        "normalized_category": "restaurants",
                        "percent": 3.0,
                        "source_type": "imported",
                        "monthly_limit": None,
                    },
                ],
            },
        ],
    }

    use_case = ImportUserDataUseCase(uow_factory)
    result = await use_case.execute(user_id=user.id, payload=payload)

    assert result.banks_imported == 1
    assert result.items_imported == 2
    # Old bank is gone — replace, not merge.
    bank_names = sorted(bank.bank_name for bank in store.banks.values() if bank.user_id == user.id)
    assert bank_names == ["Tinkoff"]


@pytest.mark.asyncio
async def test_import_round_trips_with_export(uow_factory, store) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        bank = await uow.banks.create(user.id, "Sber")
        await uow.cashback.replace_for_bank(
            bank.id,
            [
                CashbackDraftItem(
                    raw_category="Аптеки",
                    normalized_category="pharmacy",
                    percent=Decimal("4.00"),
                    source_type="manual",
                    monthly_limit=Decimal("1500.00"),
                ),
            ],
        )
        await uow.commit()

    export_use_case = ExportUserDataUseCase(uow_factory)
    exported = await export_use_case.execute(user_id=user.id)
    payload_str = json.dumps(exported.to_dict(), ensure_ascii=False)

    # Drop the bank and items so we can verify the import re-creates them.
    async with uow_factory() as uow:
        existing = await uow.banks.list_for_user(user.id)
        for bank in existing:
            await uow.banks.delete(bank.id)
        await uow.commit()
    assert all(b.user_id != user.id for b in store.banks.values())

    import_use_case = ImportUserDataUseCase(uow_factory)
    result = await import_use_case.execute(user_id=user.id, payload=payload_str)
    assert result.banks_imported == 1
    assert result.items_imported == 1
    re_imported = next(b for b in store.banks.values() if b.user_id == user.id)
    items = list(store.bank_items[re_imported.id])
    assert items[0].raw_category == "Аптеки"
    assert items[0].monthly_limit == Decimal("1500.00")


@pytest.mark.asyncio
async def test_import_rejects_invalid_json_string(uow_factory) -> None:
    use_case = ImportUserDataUseCase(uow_factory)
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=1, payload="this is not json")
    assert error.value.message_key == "errors.import_invalid_json"


@pytest.mark.asyncio
async def test_import_rejects_payload_without_banks_array(uow_factory) -> None:
    use_case = ImportUserDataUseCase(uow_factory)
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=1, payload={"schema_version": 1})
    assert error.value.message_key == "errors.import_invalid_payload"


@pytest.mark.asyncio
async def test_import_rejects_too_many_banks(uow_factory) -> None:
    use_case = ImportUserDataUseCase(uow_factory)
    payload = {
        "schema_version": 1,
        "banks": [{"bank_name": f"Bank{i}", "items": []} for i in range(101)],
    }
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=1, payload=payload)
    assert error.value.message_key == "errors.import_too_many_banks"


@pytest.mark.asyncio
async def test_import_skips_invalid_items_keeps_valid_ones(uow_factory, store) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        await uow.commit()

    payload = {
        "schema_version": 1,
        "banks": [
            {
                "bank_name": "Tinkoff",
                "items": [
                    {"raw_category": "АЗС", "normalized_category": "fuel", "percent": "5"},
                    {"raw_category": "", "normalized_category": "fuel", "percent": "5"},
                    {"raw_category": "X", "normalized_category": "y", "percent": "150"},
                    {"raw_category": "Рестораны", "normalized_category": "restaurants", "percent": "3"},
                ],
            },
        ],
    }
    use_case = ImportUserDataUseCase(uow_factory)
    result = await use_case.execute(user_id=user.id, payload=payload)
    assert result.banks_imported == 1
    assert result.items_imported == 2
    assert len(result.skipped_items) == 2
