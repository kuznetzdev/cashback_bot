from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.use_cases.quick_add_bank import QuickAddBankUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.domain.errors import ValidationError
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService


@pytest.fixture()
def use_case(uow_factory):
    parser = ParserService(CategoryService())
    return QuickAddBankUseCase(parser, SaveBankDraftUseCase(uow_factory))


@pytest.fixture()
async def user(store):
    from app.domain.models import UserAccount

    account = UserAccount(id=store.next_user_id, display_name="U", language="ru", notifications_enabled=True)
    store.users[account.id] = account
    store.next_user_id += 1
    return account


@pytest.mark.asyncio
async def test_quick_add_bank_parses_colon_and_commas(store, use_case, user):
    result = await use_case.execute(
        user_id=user.id,
        payload="Tinkoff: АЗС 5%, Рестораны 3%",
    )

    assert result.bank_name == "Tinkoff"
    assert len(result.items) == 2
    percents = {item.raw_category: item.percent for item in result.items}
    assert percents["АЗС"] == Decimal("5.00")
    assert percents["Рестораны"] == Decimal("3.00")
    # Items are actually persisted — check store state directly.
    stored_items = store.bank_items[result.bank_id]
    assert len(stored_items) == 2


@pytest.mark.asyncio
async def test_quick_add_bank_accepts_semicolons_and_newlines(store, use_case, user):
    result = await use_case.execute(
        user_id=user.id,
        payload="Alfa:\nАЗС 5%;\nРестораны 3%",
    )

    assert result.bank_name == "Alfa"
    assert {item.raw_category for item in result.items} == {"АЗС", "Рестораны"}


@pytest.mark.asyncio
async def test_quick_add_bank_rejects_missing_bank_name(use_case, user):
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=user.id, payload="АЗС 5%")
    assert error.value.message_key == "errors.invalid_bank_name"


@pytest.mark.asyncio
async def test_quick_add_bank_rejects_empty_items(use_case, user):
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=user.id, payload="Tinkoff:   ")
    assert error.value.message_key == "errors.invalid_bank_name"


@pytest.mark.asyncio
async def test_quick_add_bank_rejects_unparsable_items(use_case, user):
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=user.id, payload="Tinkoff: blah blah, nonsense")
    assert error.value.message_key == "errors.invalid_manual_input"


@pytest.mark.asyncio
async def test_quick_add_bank_rejects_empty_payload(use_case, user):
    with pytest.raises(ValidationError) as error:
        await use_case.execute(user_id=user.id, payload="")
    assert error.value.message_key == "errors.invalid_bank_name"


@pytest.mark.asyncio
async def test_quick_add_bank_accepts_dash_separator(store, use_case, user):
    result = await use_case.execute(user_id=user.id, payload="Raiffeisen - АЗС 5%")
    assert result.bank_name == "Raiffeisen"
    assert len(result.items) == 1


@pytest.mark.asyncio
async def test_quick_add_bank_updates_existing_bank(store, use_case, user):
    # Adding twice must replace the previous items, not duplicate them.
    first = await use_case.execute(user_id=user.id, payload="Tinkoff: АЗС 5%")
    second = await use_case.execute(user_id=user.id, payload="Tinkoff: Рестораны 10%")

    assert first.bank_id == second.bank_id
    stored_items = store.bank_items[second.bank_id]
    assert len(stored_items) == 1
    assert stored_items[0].raw_category == "Рестораны"
