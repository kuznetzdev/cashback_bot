from __future__ import annotations

"""Configuration module for cashback bot."""
from functools import lru_cache
from pathlib import Path
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Environment-driven settings."""

    bot_token: str = Field(..., env="BOT_TOKEN")
    database_path: Path = Field(default=Path("./data/cashback.sqlite3"), env="DB_PATH")
    locale: str = Field(default="ru", env="LOCALE")
    scheduler_timezone: str = Field(default="UTC", env="TZ")
    ocr_workers: int = Field(default=2, env="OCR_WORKERS")
    temp_dir: Path = Field(default=Path("./data/tmp"), env="TEMP_DIR")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def load_settings() -> Settings:
    return Settings()
