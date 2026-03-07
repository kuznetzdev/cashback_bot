from __future__ import annotations

from pathlib import Path


REQUIRED_ENV_KEYS = {
    "BOT_TOKEN",
    "TELEGRAM_BOT_USERNAME",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_ADMIN_DB",
    "DATABASE_URL",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT",
    "DB_POOL_RECYCLE",
    "TESSERACT_PATH",
    "LANG_DEFAULT",
    "OCR_TIMEOUT",
    "MAX_FILE_SIZE",
    "APP_TIMEZONE",
    "REMINDER_HOUR",
    "DB_CONNECT_MAX_ATTEMPTS",
    "DB_CONNECT_RETRY_DELAY",
    "TELEGRAM_RETRY_DELAY",
    "AUTO_CREATE_DB",
    "AUTO_MIGRATE",
    "MIGRATION_MAX_ATTEMPTS",
    "MIGRATION_RETRY_DELAY",
    "APP_ENABLE_TELEGRAM",
    "APP_ENABLE_WEB",
    "WEB_HOST",
    "WEB_PORT",
    "WEB_BASE_URL",
    "WEB_SESSION_SECRET",
    "WEB_SECURE_COOKIES",
    "WEB_MAX_UPLOAD_SIZE",
    "LOG_LEVEL",
    "TEMP_DIR",
}


def test_env_example_contains_required_keys() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env.example"
    content = env_path.read_text(encoding="utf-8")
    keys = {
        line.split("=", maxsplit=1)[0].strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    }
    missing = sorted(REQUIRED_ENV_KEYS - keys)
    assert not missing, f".env.example missing required keys: {missing}"
