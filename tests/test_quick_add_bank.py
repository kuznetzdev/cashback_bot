from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.use_cases.quick_add_bank import QuickAddBankUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.domain.errors import ValidationError
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService


@pytest.fixture()
def categories():
    return CategoryService()


@pytest.fixture()
def use_case(uow_factory, categories):
    parser = ParserService(categories)
    return QuickAddBankUseCase(
        parser,
        SaveBankDraftUseCase(uow_factory),
        categories=categories,
        uow_factory=uow_factory,
    )


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


@pytest.mark.asyncio
async def test_quick_add_bank_handles_multi_bank_batch(store, use_case, user):
    payload = (
        "Тинькофф:\n"
        "АЗС 5%, Рестораны 3%\n"
        "\n"
        "Сбер:\n"
        "Супермаркеты 10%, Аптеки 7%"
    )
    result = await use_case.execute(user_id=user.id, payload=payload)

    assert result.batch is not None
    # Both banks were parsed and persisted.
    assert set(result.batch.added) == {"Тинькофф", "Сбер"}
    assert len(result.batch.banks) == 2
    # First bank's result still surfaces at the top-level for legacy callers.
    assert result.bank_name == "Тинькофф"
    # Two banks end up in the store; each with two items.
    bank_names = {bank.bank_name for bank in store.banks.values()}
    assert bank_names == {"Тинькофф", "Сбер"}
    for bank in store.banks.values():
        assert len(store.bank_items[bank.id]) == 2


@pytest.mark.asyncio
async def test_quick_add_bank_reports_updated_on_existing_bank(store, use_case, user):
    await use_case.execute(user_id=user.id, payload="Tinkoff: АЗС 5%")
    result = await use_case.execute(user_id=user.id, payload="Tinkoff: Рестораны 7%")
    assert result.batch is not None
    assert result.batch.updated == ["Tinkoff"]
    assert result.batch.added == []


@pytest.mark.asyncio
async def test_quick_add_bank_warns_on_unknown_category_with_suggestion(
    store, use_case, user
):
    # "Грумминговая" is deliberately far enough from any category slug that
    # the parser's own 80%-cutoff fuzzy match doesn't claim it, but close
    # enough to "groceries"/"гадж..." that our 60%-cutoff suggestion does.
    result = await use_case.execute(user_id=user.id, payload="Тинькофф: Грумминговая 5%")
    assert result.batch is not None
    joined = "\n".join(result.batch.warnings)
    assert "Не распознано" in joined


@pytest.mark.asyncio
async def test_quick_add_bank_suggests_close_match_for_unknown_input(
    store, use_case, user
):
    # A truly unknown made-up category: the normalizer returns a raw slug
    # (not in the known set), and the 60%-cutoff suggestion may or may not
    # fire, but the "Не распознано" warning must still surface.
    result = await use_case.execute(
        user_id=user.id, payload="Тинькофф: АБРАКАДАБРА 5%"
    )
    assert result.batch is not None
    joined = "\n".join(result.batch.warnings)
    assert "АБРАКАДАБРА" in joined
    assert "Не распознано" in joined


@pytest.mark.asyncio
async def test_quick_add_bank_warns_on_high_percent(store, use_case, user):
    result = await use_case.execute(user_id=user.id, payload="Tinkoff: АЗС 50%")
    assert result.batch is not None
    joined = "\n".join(result.batch.warnings)
    assert "50" in joined
    assert "высокий" in joined.lower()
