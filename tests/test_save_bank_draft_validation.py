from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.use_cases.save_bank_draft import (
    _MAX_BANK_NAME_LENGTH,
    _MAX_ITEMS_PER_BANK,
    SaveBankDraftUseCase,
)
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem


def _items(n: int = 1, percent: Decimal = Decimal("5")) -> list[CashbackDraftItem]:
    return [
        CashbackDraftItem(
            raw_category=f"cat-{i}",
            normalized_category=f"slug_{i}",
            percent=percent,
            source_type="manual",
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_save_bank_rejects_overly_long_bank_name(uow_factory) -> None:
    use_case = SaveBankDraftUseCase(uow_factory)
    overlong = "x" * (_MAX_BANK_NAME_LENGTH + 1)
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=1, bank_id=None, bank_name=overlong, items=_items())
    assert error.value.message_key == "errors.bank_name_too_long"
    assert error.value.payload == {"max_length": _MAX_BANK_NAME_LENGTH}


@pytest.mark.asyncio
async def test_save_bank_rejects_too_many_items(uow_factory) -> None:
    use_case = SaveBankDraftUseCase(uow_factory)
    too_many = _items(n=_MAX_ITEMS_PER_BANK + 1)
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=1, bank_id=None, bank_name="Tinkoff", items=too_many)
    assert error.value.message_key == "errors.too_many_items"
    assert error.value.payload == {"max_items": _MAX_ITEMS_PER_BANK}


@pytest.mark.asyncio
async def test_save_bank_rejects_percent_above_100(uow_factory) -> None:
    use_case = SaveBankDraftUseCase(uow_factory)
    items = _items(n=1, percent=Decimal("150"))
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=1, bank_id=None, bank_name="Tinkoff", items=items)
    assert error.value.message_key == "errors.percent_out_of_range"


@pytest.mark.asyncio
async def test_save_bank_accepts_exactly_100_percent(store, uow_factory) -> None:
    use_case = SaveBankDraftUseCase(uow_factory)
    # First we need a user.
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        await uow.commit()
    items = _items(n=1, percent=Decimal("100"))
    bank_id = await use_case.execute(
        user_id=user.id, bank_id=None, bank_name="Tinkoff", items=items
    )
    assert bank_id in store.banks


@pytest.mark.asyncio
async def test_save_bank_strips_whitespace_from_bank_name(store, uow_factory) -> None:
    use_case = SaveBankDraftUseCase(uow_factory)
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        await uow.commit()
    bank_id = await use_case.execute(
        user_id=user.id, bank_id=None, bank_name="  Tinkoff  ", items=_items()
    )
    assert store.banks[bank_id].bank_name == "Tinkoff"


@pytest.mark.asyncio
async def test_save_bank_accepts_max_length_name(store, uow_factory) -> None:
    use_case = SaveBankDraftUseCase(uow_factory)
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        await uow.commit()
    name = "x" * _MAX_BANK_NAME_LENGTH
    bank_id = await use_case.execute(
        user_id=user.id, bank_id=None, bank_name=name, items=_items()
    )
    assert bank_id in store.banks
