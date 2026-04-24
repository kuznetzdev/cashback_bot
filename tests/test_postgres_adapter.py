from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.adapters.postgres.models import Base, UserModel
from app.adapters.postgres.uow import build_uow_factory
from app.application.months import current_month_key, shift_month_key
from app.domain.models import CashbackDraftItem


@pytest.mark.asyncio
async def test_postgres_uow_implements_ports_with_atomic_replace_and_delete() -> None:
    current_month = current_month_key()
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
        user = await uow.users.create(display_name="Postgres User", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="777",
            provider_username="postgres-user",
            provider_display_name="Postgres User",
        )
        bank = await uow.banks.create(user.id, "Adapter Bank")
        await uow.cashback.replace_for_bank(
            bank.id,
            current_month,
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
            current_month,
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
        items = await uow.cashback.list_for_bank(banks[0].id, current_month)
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
    current_month = current_month_key()
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
        user_a = await uow.users.create(display_name="User A", default_language="ru")
        user_b = await uow.users.create(display_name="User B", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user_a.id,
            provider="telegram",
            provider_user_id="101",
            provider_username="user-a",
            provider_display_name="User A",
        )
        await uow.identities.upsert_for_user(
            user_id=user_b.id,
            provider="telegram",
            provider_user_id="202",
            provider_username="user-b",
            provider_display_name="User B",
        )
        bank_a = await uow.banks.create(user_a.id, "Shared Name")
        bank_b = await uow.banks.create(user_b.id, "Shared Name")
        await uow.cashback.replace_for_bank(
            bank_a.id,
            current_month,
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
            current_month,
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
        items_a = await uow.cashback.list_for_bank(banks_a[0].id, current_month)
        items_b = await uow.cashback.list_for_bank(banks_b[0].id, current_month)
        assert len(items_a) == 1 and items_a[0].normalized_category == "fuel"
        assert len(items_b) == 1 and items_b[0].normalized_category == "restaurants"

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_uow_keeps_separate_month_snapshots() -> None:
    current_month = current_month_key()
    next_month = shift_month_key(current_month, 1)
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
        user = await uow.users.create(display_name="Month User", default_language="ru")
        bank = await uow.banks.create(user.id, "Adapter Bank")
        await uow.cashback.replace_for_bank(
            bank.id,
            current_month,
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
            next_month,
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
        current_items = await uow.cashback.list_for_bank(bank.id, current_month)
        next_items = await uow.cashback.list_for_bank(bank.id, next_month)
        months = await uow.cashback.list_months_for_bank(bank.id)

    assert [item.normalized_category for item in current_items] == ["fuel"]
    assert [item.normalized_category for item in next_items] == ["restaurants"]
    assert months == [current_month, next_month]

    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_identity_upsert_does_not_mirror_into_legacy_telegram_columns() -> None:
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
        user = await uow.users.create(display_name="Legacy Seam", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="777",
            provider_username="tg-user",
            provider_display_name="Telegram User",
        )
        await uow.commit()

    async with session_factory() as session:
        result = await session.execute(select(UserModel).where(UserModel.id == user.id))
        model = result.scalar_one()
        assert model.telegram_user_id is None
        assert model.username is None
        assert model.full_name is None

    await engine.dispose()
