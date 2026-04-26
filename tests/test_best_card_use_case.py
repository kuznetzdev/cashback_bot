from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.use_cases.best_card_for_category import BestCardForCategoryUseCase
from app.domain.models import CashbackDraftItem
from app.domain.services.categories import CategoryService
from app.domain.services.ranking import RankingService


@pytest.fixture
def use_case(uow_factory):
    categories = CategoryService()
    ranking = RankingService(categories)
    return BestCardForCategoryUseCase(uow_factory, ranking, categories)


async def _seed(store, *, banks: dict[str, list[tuple[str, Decimal]]]) -> int:
    user = await _seed_user(store)
    for bank_name, items in banks.items():
        bank = await _seed_bank(store, user.id, bank_name)
        store.bank_items[bank.id] = [
            CashbackDraftItem(
                raw_category=category,
                normalized_category=CategoryService().normalize(category).slug,
                percent=percent,
                source_type="manual",
            )
            for category, percent in items
        ]
    return user.id


async def _seed_user(store):
    from app.domain.models import UserAccount

    user = UserAccount(id=store.next_user_id, display_name="U", language="ru", notifications_enabled=True)
    store.users[user.id] = user
    store.next_user_id += 1
    return user


async def _seed_bank(store, user_id: int, bank_name: str):
    from app.domain.models import Bank

    bank = Bank(id=store.next_bank_id, user_id=user_id, bank_name=bank_name)
    store.banks[bank.id] = bank
    store.next_bank_id += 1
    return bank


@pytest.mark.asyncio
async def test_best_card_returns_leader_for_direct_category_match(store, use_case):
    user_id = await _seed(
        store,
        banks={
            "Tinkoff": [("АЗС", Decimal("5"))],
            "Alfa": [("Рестораны", Decimal("10"))],
        },
    )

    result = await use_case.execute(user_id=user_id, query="рестораны", language="ru")

    assert result.leader is not None
    assert result.leader.best_percent == Decimal("10")
    assert result.leader.bank_names == ["Alfa"]
    assert result.normalized_slug == "restaurants"


@pytest.mark.asyncio
async def test_best_card_expands_related_slugs(store, use_case):
    # User has 'groceries'-slug entries but asks about 'supermarkets' — the
    # expand_query_slugs logic must bridge them.
    user_id = await _seed(
        store,
        banks={"Sber": [("продукты питания", Decimal("7"))]},
    )

    result = await use_case.execute(user_id=user_id, query="supermarkets", language="en")

    assert result.leader is not None
    assert result.leader.best_percent == Decimal("7")


@pytest.mark.asyncio
async def test_best_card_returns_none_when_no_banks(store, use_case):
    user = await _seed_user(store)

    result = await use_case.execute(user_id=user.id, query="рестораны", language="ru")

    assert result.leader is None
    assert result.normalized_slug == "restaurants"


@pytest.mark.asyncio
async def test_best_card_returns_none_when_nothing_matches(store, use_case):
    user_id = await _seed(
        store,
        banks={"Tinkoff": [("АЗС", Decimal("5"))]},
    )

    result = await use_case.execute(user_id=user_id, query="кино", language="ru")

    assert result.leader is None
    assert result.normalized_slug == "movies"


@pytest.mark.asyncio
async def test_best_card_blank_query_does_not_hit_ranking(store, use_case):
    user_id = await _seed(
        store,
        banks={"Tinkoff": [("АЗС", Decimal("5"))]},
    )

    result = await use_case.execute(user_id=user_id, query="   ", language="ru")

    assert result.leader is None
    assert result.normalized_slug == ""


@pytest.mark.asyncio
async def test_best_card_ties_return_all_bank_names(store, use_case):
    user_id = await _seed(
        store,
        banks={
            "Tinkoff": [("АЗС", Decimal("5"))],
            "Alfa": [("АЗС", Decimal("5"))],
        },
    )

    result = await use_case.execute(user_id=user_id, query="АЗС", language="ru")

    assert result.leader is not None
    assert result.leader.bank_names == ["Alfa", "Tinkoff"]
