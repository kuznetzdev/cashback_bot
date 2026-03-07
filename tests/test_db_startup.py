from __future__ import annotations

import pytest

from app.bootstrap.config import Settings
from app.bootstrap import db_startup


class FakeConnection:
    def __init__(self, *, exists: bool) -> None:
        self.exists = exists
        self.executed: list[str] = []
        self.closed = False

    async def fetchval(self, _query: str, _db_name: str | None = None):
        return 1 if self.exists else None

    async def execute(self, sql: str) -> None:
        self.executed.append(sql)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_ensure_database_exists_creates_missing_database(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        BOT_TOKEN="123456:TEST_TOKEN",
        POSTGRES_DB="cashback_bot",
        DB_CONNECT_MAX_ATTEMPTS=1,
        DB_CONNECT_RETRY_DELAY=0.1,
        AUTO_CREATE_DB=True,
    )
    fake_conn = FakeConnection(exists=False)

    async def _fake_connect(**_kwargs):
        return fake_conn

    monkeypatch.setattr(db_startup.asyncpg, "connect", _fake_connect)
    await db_startup.ensure_database_exists(settings)

    assert fake_conn.executed == ['CREATE DATABASE "cashback_bot"']
    assert fake_conn.closed is True


@pytest.mark.asyncio
async def test_ensure_database_exists_uses_database_url_for_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        BOT_TOKEN="123456:ok",
        DATABASE_URL="postgresql+asyncpg://user:pass@dbhost:5544/external_db",
        AUTO_CREATE_DB=True,
    )
    fake_conn = FakeConnection(exists=False)
    captured: dict[str, object] = {}

    async def _fake_connect(**kwargs):
        captured.update(kwargs)
        return fake_conn

    monkeypatch.setattr(db_startup.asyncpg, "connect", _fake_connect)
    await db_startup.ensure_database_exists(settings)
    assert captured["host"] == "dbhost"
    assert captured["port"] == 5544
    assert captured["user"] == "user"
    assert captured["password"] == "pass"
    assert captured["database"] == "postgres"
    assert fake_conn.executed == ['CREATE DATABASE "external_db"']
    assert fake_conn.closed is True


@pytest.mark.asyncio
async def test_ensure_database_exists_skips_non_postgres_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        BOT_TOKEN="123456:ok",
        DATABASE_URL="sqlite+aiosqlite:///tmp/test.db",
        AUTO_CREATE_DB=True,
    )

    async def _fake_connect(**_kwargs):
        raise AssertionError("connect should not be called for non-postgres DATABASE_URL")

    monkeypatch.setattr(db_startup.asyncpg, "connect", _fake_connect)
    await db_startup.ensure_database_exists(settings)


@pytest.mark.asyncio
async def test_ensure_database_exists_uses_custom_admin_db(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        BOT_TOKEN="123456:ok",
        POSTGRES_DB="cashback_bot",
        POSTGRES_ADMIN_DB="template1",
        DB_CONNECT_MAX_ATTEMPTS=1,
        DB_CONNECT_RETRY_DELAY=0.1,
        AUTO_CREATE_DB=True,
    )
    fake_conn = FakeConnection(exists=False)
    captured: dict[str, object] = {}

    async def _fake_connect(**kwargs):
        captured.update(kwargs)
        return fake_conn

    monkeypatch.setattr(db_startup.asyncpg, "connect", _fake_connect)
    await db_startup.ensure_database_exists(settings)

    assert captured["database"] == "template1"
    assert fake_conn.executed == ['CREATE DATABASE "cashback_bot"']


@pytest.mark.asyncio
async def test_ensure_database_exists_fallbacks_to_target_db_when_admin_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        BOT_TOKEN="123456:ok",
        POSTGRES_DB="cashback_bot",
        DB_CONNECT_MAX_ATTEMPTS=1,
        DB_CONNECT_RETRY_DELAY=0.1,
        AUTO_CREATE_DB=True,
    )
    fake_target_conn = FakeConnection(exists=True)
    connect_calls: list[str] = []

    async def _fake_connect(**kwargs):
        database = str(kwargs.get("database", ""))
        connect_calls.append(database)
        if database == "postgres":
            raise OSError("admin db is unreachable")
        if database == "cashback_bot":
            return fake_target_conn
        raise AssertionError(f"Unexpected database argument: {database}")

    monkeypatch.setattr(db_startup.asyncpg, "connect", _fake_connect)
    await db_startup.ensure_database_exists(settings)
    assert connect_calls == ["postgres", "cashback_bot"]
    assert fake_target_conn.executed == []
    assert fake_target_conn.closed is True


def test_build_create_database_sql_quotes_identifier() -> None:
    sql = db_startup._build_create_database_sql('my"db')
    assert sql == 'CREATE DATABASE "my""db"'
