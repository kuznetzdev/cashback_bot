from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.postgres.models import Base
from app.adapters.postgres.uow import build_uow_factory
from app.domain.models import CashbackDraftItem


@pytest.mark.asyncio
async def test_postgres_uow_implements_ports_with_atomic_replace_and_delete() -> None:
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
        user = await uow.users.upsert(
            external_user_id=777,
            username="postgres-user",
            full_name="Postgres User",
            default_language="ru",
        )
        bank = await uow.banks.create(user.id, "Adapter Bank")
        await uow.cashback.replace_for_bank(
            bank.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5.00"),
                    source_type="manual",
                )
            ],
        )
        await uow.cashback.replace_for_bank(
            bank.id,
            [
                CashbackDraftItem(
                    raw_category="Рестораны",
                    normalized_category="restaurants",
                    percent=Decimal("7.00"),
                    source_type="manual",
                )
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        banks = await uow.banks.list_for_user(user.id)
        assert len(banks) == 1
        items = await uow.cashback.list_for_bank(banks[0].id)
        assert len(items) == 1
        assert items[0].normalized_category == "restaurants"
        await uow.banks.delete(banks[0].id)
        await uow.commit()

    async with uow_factory() as uow:
        banks_after_delete = await uow.banks.list_for_user(user.id)
        assert banks_after_delete == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_uow_isolates_data_between_users() -> None:
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
        user_a = await uow.users.upsert(
            external_user_id=101,
            username="user-a",
            full_name="User A",
            default_language="ru",
        )
        user_b = await uow.users.upsert(
            external_user_id=202,
            username="user-b",
            full_name="User B",
            default_language="ru",
        )
        bank_a = await uow.banks.create(user_a.id, "Shared Name")
        bank_b = await uow.banks.create(user_b.id, "Shared Name")
        await uow.cashback.replace_for_bank(
            bank_a.id,
            [
                CashbackDraftItem(
                    raw_category="АЗС",
                    normalized_category="fuel",
                    percent=Decimal("5.00"),
                    source_type="manual",
                )
            ],
        )
        await uow.cashback.replace_for_bank(
            bank_b.id,
            [
                CashbackDraftItem(
                    raw_category="Рестораны",
                    normalized_category="restaurants",
                    percent=Decimal("7.00"),
                    source_type="manual",
                )
            ],
        )
        await uow.commit()

    async with uow_factory() as uow:
        banks_a = await uow.banks.list_for_user(user_a.id)
        banks_b = await uow.banks.list_for_user(user_b.id)
        assert len(banks_a) == 1
        assert len(banks_b) == 1
        assert banks_a[0].bank_name == "Shared Name"
        assert banks_b[0].bank_name == "Shared Name"
        items_a = await uow.cashback.list_for_bank(banks_a[0].id)
        items_b = await uow.cashback.list_for_bank(banks_b[0].id)
        assert len(items_a) == 1 and items_a[0].normalized_category == "fuel"
        assert len(items_b) == 1 and items_b[0].normalized_category == "restaurants"

    await engine.dispose()
