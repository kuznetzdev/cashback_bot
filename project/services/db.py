"""Asynchronous database layer for user receipts and cashback tracking."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

LOGGER = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE NOT NULL,
    language TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    cashback REAL NOT NULL,
    currency TEXT NOT NULL,
    purchase_date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass
class Receipt:
    user_id: int
    merchant: str
    category: str
    amount: float
    cashback: float
    currency: str
    purchase_date: str


class AsyncDatabase:
    """Async wrapper around SQLite with convenience helpers."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        LOGGER.info("Initializing database at %s", self._path)
        async with self._connect() as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def upsert_user(self, telegram_id: int, language: str) -> int:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Upserting user %s", telegram_id)
                await conn.execute(
                    "INSERT INTO users (telegram_id, language) VALUES (?, ?) "
                    "ON CONFLICT(telegram_id) DO UPDATE SET language=excluded.language",
                    (telegram_id, language),
                )
                await conn.commit()
                cursor = await conn.execute(
                    "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("Failed to retrieve user id after upsert")
                return int(row["id"])

    async def delete_last_receipt(self, user_id: int) -> bool:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Deleting last receipt for user %s", user_id)
                cursor = await conn.execute(
                    "SELECT id FROM receipts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                    (user_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    return False
                await conn.execute("DELETE FROM receipts WHERE id = ?", (row["id"],))
                await conn.commit()
                return True

    async def add_receipt(self, receipt: Receipt) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Adding receipt for user %s", receipt.user_id)
                await conn.execute(
                    """
                    INSERT INTO receipts (user_id, merchant, category, amount, cashback, currency, purchase_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.user_id,
                        receipt.merchant,
                        receipt.category,
                        receipt.amount,
                        receipt.cashback,
                        receipt.currency,
                        receipt.purchase_date,
                    ),
                )
                await conn.commit()

    async def list_receipts(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM receipts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def iter_category_totals(
        self, user_id: int, days: int
    ) -> AsyncIterator[tuple[str, float, float]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT category, SUM(amount) AS total_amount, SUM(cashback) AS total_cashback
                FROM receipts
                WHERE user_id = ? AND purchase_date >= date('now', ?)
                GROUP BY category
                ORDER BY total_cashback DESC
                """,
                (user_id, f"-{days} day"),
            )
            async for row in cursor:
                yield row["category"], float(row["total_amount"]), float(row["total_cashback"])

    async def list_merchants(self, user_id: int) -> list[str]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT merchant FROM receipts WHERE user_id = ? ORDER BY merchant",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [row["merchant"] for row in rows]

    async def fetch_recent_cashback(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT merchant, category, amount, cashback, currency, purchase_date
                FROM receipts
                WHERE user_id = ?
                ORDER BY purchase_date DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def purge_user(self, user_id: int) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.info("Purging data for user %s", user_id)
                await conn.execute("DELETE FROM receipts WHERE user_id = ?", (user_id,))
                await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                await conn.commit()

    async def list_users(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute("SELECT telegram_id, language FROM users")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
