from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import asyncpg
from asyncpg import Connection
from asyncpg.exceptions import DuplicateDatabaseError

from app.bootstrap.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PostgresTarget:
    host: str
    port: int
    user: str | None
    password: str | None
    database: str


async def ensure_database_exists(settings: Settings) -> None:
    if not settings.auto_create_db:
        logger.info("AUTO_CREATE_DB disabled. Skip database bootstrap.")
        return
    target = _resolve_target(settings)
    if target is None:
        return

    for attempt in range(1, settings.db_connect_max_attempts + 1):
        conn: Connection | None = None
        try:
            conn = await asyncpg.connect(
                host=target.host,
                port=target.port,
                user=target.user,
                password=target.password,
                database=settings.postgres_admin_db,
            )
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", target.database)
            if exists:
                logger.info("Database %s already exists.", target.database)
                return
            create_sql = _build_create_database_sql(target.database)
            await conn.execute(create_sql)
            logger.info("Database %s created.", target.database)
            return
        except DuplicateDatabaseError:
            logger.info("Database %s already created concurrently.", target.database)
            return
        except (OSError, asyncpg.PostgresError) as error:
            if await _can_connect_target_database(target):
                logger.info(
                    "Admin database is unavailable, but target database %s is reachable. Continue startup.",
                    target.database,
                )
                return
            logger.warning(
                "Database bootstrap failed (attempt %s/%s): %s",
                attempt,
                settings.db_connect_max_attempts,
                error,
            )
            if attempt == settings.db_connect_max_attempts:
                raise RuntimeError("Unable to auto-create database.") from error
            await asyncio.sleep(settings.db_connect_retry_delay)
        finally:
            if conn is not None:
                await conn.close()


def _build_create_database_sql(db_name: str) -> str:
    return f"CREATE DATABASE {_quote_identifier(db_name)}"


def _quote_identifier(identifier: str) -> str:
    if not identifier:
        raise ValueError("Identifier cannot be empty.")
    return '"' + identifier.replace('"', '""') + '"'


def _resolve_target(settings: Settings) -> PostgresTarget | None:
    if settings.database_url:
        target = _target_from_database_url(settings.database_url)
        if target is not None:
            return target
        logger.info("DATABASE_URL is not PostgreSQL. Skip auto-create.")
        return None
    if not settings.postgres_db:
        raise RuntimeError("POSTGRES_DB is empty.")
    return PostgresTarget(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )


def _target_from_database_url(database_url: str) -> PostgresTarget | None:
    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if not scheme.startswith("postgresql"):
        return None
    host = parsed.hostname
    if not host:
        raise RuntimeError("DATABASE_URL does not contain host.")
    database = parsed.path.lstrip("/")
    if not database:
        raise RuntimeError("DATABASE_URL does not contain database name.")
    return PostgresTarget(
        host=host,
        port=parsed.port or 5432,
        user=unquote(parsed.username) if parsed.username is not None else None,
        password=unquote(parsed.password) if parsed.password is not None else None,
        database=database,
    )


async def _can_connect_target_database(target: PostgresTarget) -> bool:
    conn: Connection | None = None
    try:
        conn = await asyncpg.connect(
            host=target.host,
            port=target.port,
            user=target.user,
            password=target.password,
            database=target.database,
        )
        await conn.fetchval("SELECT 1")
        return True
    except (OSError, asyncpg.PostgresError):
        return False
    finally:
        if conn is not None:
            await conn.close()
