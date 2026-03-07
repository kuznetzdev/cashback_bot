from __future__ import annotations

import pytest

from app.bootstrap.config import Settings
from app.bootstrap.runtime import _validate_startup_settings


def test_validate_startup_settings_rejects_placeholder_token() -> None:
    settings = Settings(BOT_TOKEN="123456:replace_me")
    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)


def test_validate_startup_settings_accepts_non_placeholder_token() -> None:
    settings = Settings(BOT_TOKEN="123456:valid_value", APP_ENABLE_TELEGRAM=True, APP_ENABLE_WEB=False)
    _validate_startup_settings(settings)


def test_validate_startup_settings_requires_at_least_one_adapter() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid_value",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=False,
    )
    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)


def test_validate_startup_settings_requires_web_username_and_secret() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid_value",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        TELEGRAM_BOT_USERNAME="",
        WEB_SESSION_SECRET="change-me-session-secret",
    )
    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)
