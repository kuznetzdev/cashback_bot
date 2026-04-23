from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(default="123456:TEST_TOKEN", alias="BOT_TOKEN")
    telegram_bot_username: str = Field(default="", alias="TELEGRAM_BOT_USERNAME")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="cashback_bot", alias="POSTGRES_DB")
    postgres_user: str = Field(default="cashback_user", alias="POSTGRES_USER")
    postgres_password: str = Field(default="cashback_password", alias="POSTGRES_PASSWORD")
    postgres_admin_db: str = Field(default="postgres", alias="POSTGRES_ADMIN_DB")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    tesseract_path: str = Field(default="tesseract", alias="TESSERACT_PATH")
    lang_default: str = Field(default="ru", alias="LANG_DEFAULT")
    ocr_timeout: int = Field(default=20, alias="OCR_TIMEOUT", ge=1, le=180)
    max_file_size: int = Field(default=5 * 1024 * 1024, alias="MAX_FILE_SIZE", ge=1024)
    ocr_provider: str = Field(default="auto", alias="OCR_PROVIDER")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-4-7", alias="ANTHROPIC_MODEL")
    claude_vision_timeout: int = Field(default=60, alias="CLAUDE_VISION_TIMEOUT", ge=5, le=180)
    claude_vision_max_tokens: int = Field(default=4096, alias="CLAUDE_VISION_MAX_TOKENS", ge=256, le=16000)
    app_timezone: str = Field(default="Europe/Moscow", alias="APP_TIMEZONE")
    reminder_hour: int = Field(default=10, alias="REMINDER_HOUR", ge=0, le=23)
    db_connect_max_attempts: int = Field(default=20, alias="DB_CONNECT_MAX_ATTEMPTS", ge=1, le=120)
    db_connect_retry_delay: float = Field(default=2.0, alias="DB_CONNECT_RETRY_DELAY", ge=0.1, le=30.0)
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE", ge=1, le=200)
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW", ge=0, le=200)
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT", ge=1, le=300)
    db_pool_recycle: int = Field(default=300, alias="DB_POOL_RECYCLE", ge=30, le=3600)
    telegram_retry_delay: float = Field(default=5.0, alias="TELEGRAM_RETRY_DELAY", ge=1.0, le=60.0)
    auto_create_db: bool = Field(default=True, alias="AUTO_CREATE_DB")
    auto_migrate: bool = Field(default=True, alias="AUTO_MIGRATE")
    migration_max_attempts: int = Field(default=10, alias="MIGRATION_MAX_ATTEMPTS", ge=1, le=120)
    migration_retry_delay: float = Field(default=2.0, alias="MIGRATION_RETRY_DELAY", ge=0.1, le=30.0)
    app_enable_telegram: bool = Field(default=True, alias="APP_ENABLE_TELEGRAM")
    app_enable_web: bool = Field(default=False, alias="APP_ENABLE_WEB")
    web_enable_telegram_auth: bool = Field(default=True, alias="WEB_ENABLE_TELEGRAM_AUTH")
    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=8080, alias="WEB_PORT", ge=1, le=65535)
    web_base_url: str = Field(default="http://localhost:8080", alias="WEB_BASE_URL")
    web_session_secret: str = Field(default="change-me-session-secret", alias="WEB_SESSION_SECRET")
    web_secure_cookies: bool = Field(default=False, alias="WEB_SECURE_COOKIES")
    web_max_upload_size: int = Field(default=5 * 1024 * 1024, alias="WEB_MAX_UPLOAD_SIZE", ge=1024)
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
