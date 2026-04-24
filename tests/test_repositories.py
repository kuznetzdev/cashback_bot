from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.postgres.models import Base
from app.adapters.postgres.uow import build_uow_factory
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


async def test_in_memory_list_ranking_entries_returns_all_items_for_user(uow_factory) -> None:
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="Ranker", default_language="ru")
        bank_one = await uow.banks.create(user.id, "Bank One")
        bank_two = await uow.banks.create(user.id, "Bank Two")
        await uow.cashback.replace_for_bank(
            bank_one.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5"),
                    source_type="manual",
                ),
                CashbackDraftItem(
                    raw_category="Рестораны",
                    normalized_category="restaurants",
                    percent=Decimal("3"),
                    source_type="manual",
                ),
            ],
        )
        await uow.cashback.replace_for_bank(
            bank_two.id,
            [
                CashbackDraftItem(
                    raw_category="Аптеки",
                    normalized_category="pharmacy",
                    percent=Decimal("4"),
                    source_type="manual",
                ),
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        entries = await uow.cashback.list_ranking_entries_for_user(user.id)
    slugs = sorted(entry.category_slug for entry in entries)
    assert slugs == ["fuel", "pharmacy", "restaurants"]
    assert len(entries) == 3
    # Every row carries both its bank and the category — proves the JOIN.
    assert {entry.bank_name for entry in entries} == {"Bank One", "Bank Two"}


@pytest.mark.asyncio
async def test_postgres_list_ranking_entries_returns_all_items_in_one_query() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uow_factory = build_uow_factory(session_factory)

    async with uow_factory() as uow:
        user = await uow.users.create(display_name="Bulk", default_language="ru")
        bank_one = await uow.banks.create(user.id, "One")
        bank_two = await uow.banks.create(user.id, "Two")
        await uow.cashback.replace_for_bank(
            bank_one.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5.00"),
                    source_type="manual",
                ),
                CashbackDraftItem(
                    raw_category="Рестораны",
                    normalized_category="restaurants",
                    percent=Decimal("3.00"),
                    source_type="manual",
                ),
            ],
        )
        await uow.cashback.replace_for_bank(
            bank_two.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("2.00"),
                    source_type="manual",
                ),
            ],
        )
        await uow.commit()

    # Count SQL SELECT statements issued by the bulk call to prove it's O(1).
    select_count = 0

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count_selects(_conn, _cursor, statement, *_args, **_kwargs):  # noqa: ANN001
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    async with uow_factory() as uow:
        entries = await uow.cashback.list_ranking_entries_for_user(user.id)

    assert len(entries) == 3
    assert select_count == 1, (
        f"Expected a single SELECT for the bulk ranking lookup, got {select_count}."
    )
    await engine.dispose()
