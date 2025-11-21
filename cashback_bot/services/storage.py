from __future__ import annotations

"""Async storage layer for cashback bot."""
import json
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional

import aiosqlite

from ..models.bank import Bank, BankCategory
from ..models.item import CashbackItem
from ..models.user_settings import UserSettings


class StorageService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def init_schema(self) -> None:
        conn = await self._connect()
        try:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    locale TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS merges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    merged_from TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ocr_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    bank_id INTEGER,
                    symbols INTEGER,
                    quality REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    locale TEXT NOT NULL,
                    daily_notifications INTEGER DEFAULT 1,
                    monthly_notifications INTEGER DEFAULT 1,
                    timezone TEXT DEFAULT 'UTC',
                    best_preferences TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            await conn.commit()
        finally:
            await conn.close()

    async def upsert_user(self, telegram_id: int, locale: str) -> int:
        conn = await self._connect()
        try:
            cursor = await conn.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,))
            row = await cursor.fetchone()
            if row:
                await conn.execute(
                    "UPDATE users SET locale=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (locale, row[0])
                )
                await conn.commit()
                return int(row[0])
            cursor = await conn.execute(
                "INSERT INTO users (telegram_id, locale) VALUES (?, ?)", (telegram_id, locale)
            )
            await conn.commit()
            return int(cursor.lastrowid)
        finally:
            await conn.close()

    async def save_bank(self, bank: Bank) -> int:
        conn = await self._connect()
        try:
            categories_json = json.dumps([category.dict() for category in bank.categories])
            cursor = await conn.execute(
                "INSERT INTO banks (user_id, name, categories_json) VALUES (?, ?, ?)",
                (bank.user_id, bank.name, categories_json),
            )
            await conn.execute(
                "INSERT INTO history (user_id, action, payload) VALUES (?, 'bank_created', ?)",
                (bank.user_id, json.dumps(bank.dict())),
            )
            await conn.commit()
            return int(cursor.lastrowid)
        finally:
            await conn.close()

    async def list_banks(self, user_id: int) -> List[Bank]:
        conn = await self._connect()
        try:
            cursor = await conn.execute("SELECT * FROM banks WHERE user_id=?", (user_id,))
            rows = await cursor.fetchall()
        finally:
            await conn.close()
        result: List[Bank] = []
        for row in rows:
            categories = [BankCategory(**data) for data in json.loads(row["categories_json"])]
            result.append(
                Bank(
                    id=row["id"],
                    user_id=row["user_id"],
                    name=row["name"],
                    categories=categories,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return result

    async def update_bank_categories(self, bank_id: int, categories: Iterable[BankCategory]) -> None:
        conn = await self._connect()
        try:
            categories_json = json.dumps([category.dict() for category in categories])
            await conn.execute(
                "UPDATE banks SET categories_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (categories_json, bank_id),
            )
            await conn.execute(
                "INSERT INTO history (user_id, action, payload) SELECT user_id, 'bank_updated', ? FROM banks WHERE id=?",
                (categories_json, bank_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def log_merge(self, user_id: int, category: str, merged_from: list[str]) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                "INSERT INTO merges (user_id, category, merged_from) VALUES (?, ?, ?)",
                (user_id, category, json.dumps(merged_from)),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def log_ocr(self, user_id: int, bank_id: Optional[int], text: str, quality: float) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                "INSERT INTO ocr_logs (user_id, bank_id, symbols, quality) VALUES (?, ?, ?, ?)",
                (user_id, bank_id, len(text), quality),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def save_settings(self, settings: UserSettings) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, locale, daily_notifications, monthly_notifications, timezone, best_preferences)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    locale=excluded.locale,
                    daily_notifications=excluded.daily_notifications,
                    monthly_notifications=excluded.monthly_notifications,
                    timezone=excluded.timezone,
                    best_preferences=excluded.best_preferences,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    settings.user_id,
                    settings.locale,
                    int(settings.daily_notifications),
                    int(settings.monthly_notifications),
                    settings.timezone,
                    json.dumps(settings.best_preferences) if settings.best_preferences else None,
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def load_settings(self, user_id: int) -> UserSettings:
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                "SELECT locale, daily_notifications, monthly_notifications, timezone, best_preferences FROM user_settings WHERE user_id=?",
                (user_id,),
            )
            row = await cursor.fetchone()
        finally:
            await conn.close()
        if row:
            return UserSettings(
                user_id=user_id,
                locale=row["locale"],
                daily_notifications=bool(row["daily_notifications"]),
                monthly_notifications=bool(row["monthly_notifications"]),
                timezone=row["timezone"],
                best_preferences=json.loads(row["best_preferences"]) if row["best_preferences"] else None,
            )
        return UserSettings(user_id=user_id)

    async def delete_bank(self, bank_id: int) -> None:
        conn = await self._connect()
        try:
            await conn.execute("DELETE FROM banks WHERE id=?", (bank_id,))
            await conn.commit()
        finally:
            await conn.close()

    async def add_history(self, user_id: int, action: str, payload: dict) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                "INSERT INTO history (user_id, action, payload) VALUES (?, ?, ?)",
                (user_id, action, json.dumps(payload)),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def list_history(self, user_id: int) -> List[dict]:
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                "SELECT action, payload, created_at FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                (user_id,),
            )
            rows = await cursor.fetchall()
        finally:
            await conn.close()
        return [dict(row) for row in rows]

    async def list_items(self, user_id: int) -> List[CashbackItem]:
        banks = await self.list_banks(user_id)
        items: List[CashbackItem] = []
        for bank in banks:
            for category in bank.active_categories():
                items.append(CashbackItem(category=category.name, rate=category.rate, bank=bank.name))
        return items
