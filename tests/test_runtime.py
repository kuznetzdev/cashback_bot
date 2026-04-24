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


def test_settings_rejects_default_session_secret_when_web_enabled() -> None:
    # Defence in depth: the model_validator added for security hardening
    # refuses to construct Settings at all when APP_ENABLE_WEB=true with the
    # shipped placeholder session secret. Ops can't accidentally boot a web
    # deployment with a known key.
    with pytest.raises(ValueError, match="WEB_SESSION_SECRET"):
        Settings(
            BOT_TOKEN="123456:valid_value",
            APP_ENABLE_TELEGRAM=False,
            APP_ENABLE_WEB=True,
            TELEGRAM_BOT_USERNAME="",
            WEB_SESSION_SECRET="change-me-session-secret",
        )


def test_validate_startup_settings_requires_web_username() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid_value",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        TELEGRAM_BOT_USERNAME="",
        WEB_SESSION_SECRET="strong-session-secret-value",
    )
    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)
