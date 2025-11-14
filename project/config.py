"""Configuration for the cashback bot project."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class BotConfig:
    """Runtime configuration loaded from environment variables."""

    token: str
    database_path: Path
    ocr_temp_dir: Path
    locale: str
    enable_notifications: bool
    analytics_window_days: int
    timezone: str


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(env: Optional[dict[str, str]] = None) -> BotConfig:
    """Load configuration from environment variables.

    Parameters
    ----------
    env: Optional[dict[str, str]]
        Optional environment dictionary. Defaults to ``os.environ`` when ``None``.
    """

    environ = env or os.environ
    token = environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is required for the bot to start")

    db_path = Path(environ.get("DB_PATH", "./data/cashback.sqlite3")).expanduser().resolve()
    ocr_temp_dir = Path(environ.get("OCR_TEMP_DIR", "./tmp/ocr"))
    locale = environ.get("DEFAULT_LOCALE", "en").lower()
    enable_notifications = _get_bool("ENABLE_NOTIFICATIONS", True)
    analytics_window_days = int(environ.get("ANALYTICS_WINDOW_DAYS", "90"))
    timezone = environ.get("BOT_TIMEZONE", "UTC")

    ocr_temp_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    return BotConfig(
        token=token,
        database_path=db_path,
        ocr_temp_dir=ocr_temp_dir,
        locale=locale,
        enable_notifications=enable_notifications,
        analytics_window_days=analytics_window_days,
        timezone=timezone,
    )
