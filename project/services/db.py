"""Extended asynchronous database layer for cashback analytics."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

LOGGER = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE NOT NULL,
    language TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    level TEXT NOT NULL DEFAULT 'Bronze',
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_bank_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

CREATE TABLE IF NOT EXISTS banks (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    locale_names TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_banks (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bank_id INTEGER REFERENCES banks(id) ON DELETE SET NULL,
    custom_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_categories (
    id INTEGER PRIMARY KEY,
    user_bank_id INTEGER NOT NULL REFERENCES user_banks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    cashback_rate REAL NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bank_categories_unique
ON bank_categories(user_bank_id, normalized_name, level);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_type TEXT NOT NULL,
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    monthly_enabled INTEGER NOT NULL DEFAULT 1,
    inactivity_warning_enabled INTEGER NOT NULL DEFAULT 1,
    inactivity_critical_enabled INTEGER NOT NULL DEFAULT 1,
    last_monthly_sent TIMESTAMP,
    last_warning_sent TIMESTAMP,
    last_critical_sent TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wizard_sessions (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    payload TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


@dataclass
class UserBank:
    id: int
    user_id: int
    custom_name: str
    bank_id: int | None = None


@dataclass
class BankCategoryRate:
    id: int
    user_bank_id: int
    name: str
    normalized_name: str
    cashback_rate: float
    level: int


@dataclass
class TemplateRecord:
    id: int
    user_id: int
    template_type: str
    name: str
    payload: str


@dataclass
class NotificationSettings:
    user_id: int
    monthly_enabled: bool
    inactivity_warning_enabled: bool
    inactivity_critical_enabled: bool
    last_monthly_sent: str | None
    last_warning_sent: str | None
    last_critical_sent: str | None


@dataclass
class WizardSession:
    user_id: int
    state: str
    payload: dict[str, Any]


_LEVEL_THRESHOLDS: Sequence[tuple[str, int]] = (
    ("Bronze", 0),
    ("Silver", 10),
    ("Gold", 30),
    ("Diamond", 60),
)


class AsyncDatabase:
    """Async wrapper around SQLite with extended domain entities."""

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
                    """
                    INSERT INTO users (telegram_id, language)
                    VALUES (?, ?)
                    ON CONFLICT(telegram_id) DO UPDATE SET language=excluded.language
                    """,
                    (telegram_id, language),
                )
                await conn.commit()
                cursor = await conn.execute(
                    "SELECT id FROM users WHERE telegram_id = ?",
                    (telegram_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("Failed to retrieve user id after upsert")
                return int(row["id"])

    async def update_last_activity(self, user_id: int, *, bank_update: bool = False) -> None:
        async with self._lock:
            async with self._connect() as conn:
                now = datetime.utcnow().isoformat()
                if bank_update:
                    LOGGER.debug("Updating bank activity timestamp for user %s", user_id)
                    await conn.execute(
                        "UPDATE users SET last_activity = ?, last_bank_update = ? WHERE id = ?",
                        (now, now, user_id),
                    )
                else:
                    LOGGER.debug("Updating activity timestamp for user %s", user_id)
                    await conn.execute(
                        "UPDATE users SET last_activity = ? WHERE id = ?",
                        (now, user_id),
                    )
                await conn.commit()

    async def increment_points(self, user_id: int, points: int) -> tuple[int, str]:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Incrementing points for user %s by %s", user_id, points)
                await conn.execute(
                    "UPDATE users SET points = points + ?, last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                    (points, user_id),
                )
                await conn.commit()
                cursor = await conn.execute(
                    "SELECT points FROM users WHERE id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("User not found when incrementing points")
                total_points = int(row["points"])
                level = self._calculate_level(total_points)
                await conn.execute(
                    "UPDATE users SET level = ? WHERE id = ?",
                    (level, user_id),
                )
                await conn.commit()
                return total_points, level

    @staticmethod
    def _calculate_level(points: int) -> str:
        level = "Bronze"
        for name, threshold in _LEVEL_THRESHOLDS:
            if points >= threshold:
                level = name
            else:
                break
        return level

    async def fetch_user_profile(self, user_id: int) -> dict[str, Any] | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT telegram_id, language, points, level, last_activity, last_bank_update
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

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
                yield (
                    row["category"],
                    float(row["total_amount"]),
                    float(row["total_cashback"]),
                )

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

    async def list_users(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT id, telegram_id, language, last_activity, last_bank_update FROM users"
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

    # --- Banks and categories -------------------------------------------------

    async def list_banks(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute("SELECT id, name, locale_names FROM banks ORDER BY name")
            rows = await cursor.fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                locale_names = json.loads(row["locale_names"] or "{}")
                result.append({"id": row["id"], "name": row["name"], "locale_names": locale_names})
            return result

    async def ensure_bank(self, name: str, locale_names: dict[str, str] | None = None) -> int:
        async with self._lock:
            async with self._connect() as conn:
                locale_json = json.dumps(locale_names or {})
                await conn.execute(
                    """
                    INSERT INTO banks (name, locale_names)
                    VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET locale_names=excluded.locale_names
                    """,
                    (name, locale_json),
                )
                await conn.commit()
                cursor = await conn.execute(
                    "SELECT id FROM banks WHERE name = ?",
                    (name,),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("Failed to ensure bank entry")
                return int(row["id"])

    async def create_user_bank(
        self, user_id: int, custom_name: str, bank_id: int | None = None
    ) -> int:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Creating bank '%s' for user %s", custom_name, user_id)
                cursor = await conn.execute(
                    """
                    INSERT INTO user_banks (user_id, bank_id, custom_name)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, bank_id, custom_name),
                )
                await conn.commit()
                user_bank_id = cursor.lastrowid
                await conn.execute(
                    "UPDATE users SET last_bank_update = CURRENT_TIMESTAMP WHERE id = ?",
                    (user_id,),
                )
                await conn.commit()
                return int(user_bank_id)

    async def update_user_bank_name(self, user_bank_id: int, custom_name: str) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Renaming user bank %s -> %s", user_bank_id, custom_name)
                await conn.execute(
                    "UPDATE user_banks SET custom_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (custom_name, user_bank_id),
                )
                await conn.commit()

    async def delete_user_bank(self, user_bank_id: int) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.info("Deleting user bank %s", user_bank_id)
                await conn.execute("DELETE FROM user_banks WHERE id = ?", (user_bank_id,))
                await conn.commit()

    async def list_user_banks(self, user_id: int) -> list[UserBank]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT id, user_id, custom_name, bank_id FROM user_banks WHERE user_id = ? ORDER BY custom_name",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [
                UserBank(
                    id=int(row["id"]),
                    user_id=int(row["user_id"]),
                    custom_name=row["custom_name"],
                    bank_id=int(row["bank_id"]) if row["bank_id"] is not None else None,
                )
                for row in rows
            ]

    async def replace_bank_categories(
        self, user_bank_id: int, categories: Iterable[tuple[str, str, float, int]]
    ) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.debug("Replacing categories for user bank %s", user_bank_id)
                await conn.execute(
                    "DELETE FROM bank_categories WHERE user_bank_id = ?",
                    (user_bank_id,),
                )
                await conn.executemany(
                    """
                    INSERT INTO bank_categories (user_bank_id, name, normalized_name, cashback_rate, level)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (user_bank_id, name, normalized, rate, level)
                        for name, normalized, rate, level in categories
                    ],
                )
                await conn.execute(
                    "UPDATE user_banks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (user_bank_id,),
                )
                await conn.commit()

    async def fetch_bank_categories(self, user_bank_id: int) -> list[BankCategoryRate]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, user_bank_id, name, normalized_name, cashback_rate, level
                FROM bank_categories
                WHERE user_bank_id = ?
                ORDER BY level, cashback_rate DESC
                """,
                (user_bank_id,),
            )
            rows = await cursor.fetchall()
            return [
                BankCategoryRate(
                    id=int(row["id"]),
                    user_bank_id=int(row["user_bank_id"]),
                    name=row["name"],
                    normalized_name=row["normalized_name"],
                    cashback_rate=float(row["cashback_rate"]),
                    level=int(row["level"]),
                )
                for row in rows
            ]

    async def fetch_all_category_rates(self, user_id: int) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    ub.id AS user_bank_id,
                    ub.custom_name AS bank_name,
                    bc.name,
                    bc.normalized_name,
                    bc.cashback_rate,
                    bc.level
                FROM bank_categories bc
                JOIN user_banks ub ON ub.id = bc.user_bank_id
                WHERE ub.user_id = ?
                ORDER BY bc.cashback_rate DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # --- Templates ------------------------------------------------------------

    async def list_templates(self, user_id: int) -> list[TemplateRecord]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, user_id, template_type, name, payload
                FROM templates
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [
                TemplateRecord(
                    id=int(row["id"]),
                    user_id=int(row["user_id"]),
                    template_type=row["template_type"],
                    name=row["name"],
                    payload=row["payload"],
                )
                for row in rows
            ]

    async def upsert_template(
        self, user_id: int, template_type: str, name: str, payload: dict[str, Any], template_id: int | None = None
    ) -> int:
        payload_json = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            async with self._connect() as conn:
                if template_id is None:
                    LOGGER.debug("Creating template '%s' for user %s", name, user_id)
                    cursor = await conn.execute(
                        """
                        INSERT INTO templates (user_id, template_type, name, payload)
                        VALUES (?, ?, ?, ?)
                        """,
                        (user_id, template_type, name, payload_json),
                    )
                    await conn.commit()
                    return int(cursor.lastrowid)
                LOGGER.debug("Updating template %s for user %s", template_id, user_id)
                await conn.execute(
                    """
                    UPDATE templates
                    SET template_type = ?, name = ?, payload = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                    """,
                    (template_type, name, payload_json, template_id, user_id),
                )
                await conn.commit()
                return template_id

    async def delete_template(self, user_id: int, template_id: int) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.info("Deleting template %s for user %s", template_id, user_id)
                await conn.execute(
                    "DELETE FROM templates WHERE id = ? AND user_id = ?",
                    (template_id, user_id),
                )
                await conn.commit()

    # --- Activity log ---------------------------------------------------------

    async def log_activity(self, user_id: int, action: str, metadata: dict[str, Any] | None = None) -> None:
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        async with self._lock:
            async with self._connect() as conn:
                await conn.execute(
                    "INSERT INTO activity_log (user_id, action, metadata) VALUES (?, ?, ?)",
                    (user_id, action, payload),
                )
                await conn.commit()

    async def list_activity(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT action, metadata, created_at
                FROM activity_log
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                metadata = json.loads(row["metadata"] or "{}")
                result.append(
                    {
                        "action": row["action"],
                        "metadata": metadata,
                        "created_at": row["created_at"],
                    }
                )
            return result

    async def clear_activity(self, user_id: int) -> None:
        async with self._lock:
            async with self._connect() as conn:
                LOGGER.info("Clearing activity log for user %s", user_id)
                await conn.execute("DELETE FROM activity_log WHERE user_id = ?", (user_id,))
                await conn.commit()

    # --- Notification settings ------------------------------------------------

    async def get_notification_settings(self, user_id: int) -> NotificationSettings:
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    monthly_enabled,
                    inactivity_warning_enabled,
                    inactivity_critical_enabled,
                    last_monthly_sent,
                    last_warning_sent,
                    last_critical_sent
                FROM notification_settings
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                LOGGER.debug("Creating default notification settings for user %s", user_id)
                await self.update_notification_settings(user_id, True, True, True)
                return NotificationSettings(user_id, True, True, True, None, None, None)
            return NotificationSettings(
                user_id=user_id,
                monthly_enabled=bool(row["monthly_enabled"]),
                inactivity_warning_enabled=bool(row["inactivity_warning_enabled"]),
                inactivity_critical_enabled=bool(row["inactivity_critical_enabled"]),
                last_monthly_sent=row["last_monthly_sent"],
                last_warning_sent=row["last_warning_sent"],
                last_critical_sent=row["last_critical_sent"],
            )

    async def update_notification_settings(
        self,
        user_id: int,
        monthly_enabled: bool,
        inactivity_warning_enabled: bool,
        inactivity_critical_enabled: bool,
    ) -> None:
        async with self._lock:
            async with self._connect() as conn:
                await conn.execute(
                    """
                    INSERT INTO notification_settings (
                        user_id, monthly_enabled, inactivity_warning_enabled, inactivity_critical_enabled
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        monthly_enabled=excluded.monthly_enabled,
                        inactivity_warning_enabled=excluded.inactivity_warning_enabled,
                        inactivity_critical_enabled=excluded.inactivity_critical_enabled,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        user_id,
                        int(monthly_enabled),
                        int(inactivity_warning_enabled),
                        int(inactivity_critical_enabled),
                    ),
                )
                await conn.commit()

    async def mark_notification_sent(self, user_id: int, notification_type: str) -> None:
        column_map = {
            "monthly": "last_monthly_sent",
            "warning": "last_warning_sent",
            "critical": "last_critical_sent",
        }
        column = column_map.get(notification_type)
        if column is None:
            raise ValueError(f"Unknown notification type: {notification_type}")
        async with self._lock:
            async with self._connect() as conn:
                await conn.execute(
                    f"UPDATE notification_settings SET {column} = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (user_id,),
                )
                await conn.commit()

    # --- Wizard sessions ------------------------------------------------------

    async def get_wizard_session(self, user_id: int) -> WizardSession | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT state, payload FROM wizard_sessions WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload"] or "{}")
            return WizardSession(user_id=user_id, state=row["state"], payload=payload)

    async def save_wizard_session(self, user_id: int, state: str, payload: dict[str, Any]) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False)
        async with self._lock:
            async with self._connect() as conn:
                await conn.execute(
                    """
                    INSERT INTO wizard_sessions (user_id, state, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        state=excluded.state,
                        payload=excluded.payload,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (user_id, state, payload_json),
                )
                await conn.commit()

    async def delete_wizard_session(self, user_id: int) -> None:
        async with self._lock:
            async with self._connect() as conn:
                await conn.execute(
                    "DELETE FROM wizard_sessions WHERE user_id = ?",
                    (user_id,),
                )
                await conn.commit()

