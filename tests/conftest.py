from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.db.repositories.users import UsersRepository
from app.infrastructure.container import build_container


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def app_container(session_factory, tmp_path: Path):
    settings = Settings(
        bot_token="TEST_TOKEN",
        database_url="sqlite+aiosqlite://",
        temp_dir=tmp_path / "ocr",
    )
    return build_container(settings, session_factory)


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_user(session: AsyncSession):
    user = await UsersRepository(session).upsert(
        telegram_user_id=101,
        username="tester",
        full_name="Test User",
        default_language="ru",
    )
    await session.flush()
    return user
