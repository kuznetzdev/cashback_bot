from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(default="123456:TEST_TOKEN", alias="BOT_TOKEN")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="cashback_bot", alias="POSTGRES_DB")
    postgres_user: str = Field(default="cashback_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="cashback_password", alias="POSTGRES_PASSWORD")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    tesseract_path: str = Field(default="tesseract", alias="TESSERACT_PATH")
    lang_default: str = Field(default="ru", alias="LANG_DEFAULT")
    ocr_timeout: int = Field(default=20, alias="OCR_TIMEOUT", ge=1, le=120)
    max_file_size: int = Field(default=5 * 1024 * 1024, alias="MAX_FILE_SIZE", ge=1024)
    app_timezone: str = Field(default="Europe/Moscow", alias="APP_TIMEZONE")
    reminder_hour: int = Field(default=10, alias="REMINDER_HOUR", ge=0, le=23)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    temp_dir: Path = Field(default=Path("ocr_tmp"), alias="TEMP_DIR")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
