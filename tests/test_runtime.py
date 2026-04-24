from __future__ import annotations

import pytest

from app.bootstrap.config import Settings
from app.bootstrap.runtime import _reminder_delivery_runtime_enabled, _validate_startup_settings


def test_validate_startup_settings_rejects_placeholder_token_when_telegram_features_are_enabled() -> None:
    settings = Settings(
        BOT_TOKEN="123456:replace_me",
        APP_ENABLE_TELEGRAM=True,
        APP_ENABLE_WEB=False,
    )
    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)


def test_validate_startup_settings_allows_placeholder_token_in_local_web_only_mode() -> None:
    settings = Settings(
        BOT_TOKEN="123456:replace_me",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        WEB_ENABLE_TELEGRAM_AUTH=False,
        REMINDER_DELIVERY_PROVIDER="",
        WEB_SESSION_SECRET="dev-session-secret-not-for-production",
    )
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
        WEB_ENABLE_TELEGRAM_AUTH=True,
        TELEGRAM_BOT_USERNAME="",
        WEB_SESSION_SECRET="change-me-session-secret",
    )
    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)


def test_validate_startup_settings_rejects_unknown_reminder_provider() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid_value",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        WEB_ENABLE_TELEGRAM_AUTH=False,
        WEB_SESSION_SECRET="dev-session-secret-not-for-production",
        REMINDER_DELIVERY_PROVIDER="email",
    )

    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)


def test_reminder_delivery_runtime_is_enabled_for_explicit_provider() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid_value",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        WEB_ENABLE_TELEGRAM_AUTH=False,
        WEB_SESSION_SECRET="dev-session-secret-not-for-production",
        REMINDER_DELIVERY_PROVIDER="telegram",
    )

    assert _reminder_delivery_runtime_enabled("telegram") is True
    _validate_startup_settings(settings)


def test_validate_startup_settings_requires_token_for_explicit_telegram_reminder_provider() -> None:
    settings = Settings(
        BOT_TOKEN="123456:replace_me",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        WEB_ENABLE_TELEGRAM_AUTH=False,
        WEB_SESSION_SECRET="dev-session-secret-not-for-production",
        REMINDER_DELIVERY_PROVIDER="telegram",
    )

    with pytest.raises(RuntimeError):
        _validate_startup_settings(settings)


def test_reminder_delivery_runtime_is_disabled_for_local_web_only_mode() -> None:
    settings = Settings(
        BOT_TOKEN="123456:TEST_TOKEN",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        WEB_ENABLE_TELEGRAM_AUTH=False,
        WEB_SESSION_SECRET="dev-session-secret-not-for-production",
        REMINDER_DELIVERY_PROVIDER="",
    )

    assert _reminder_delivery_runtime_enabled(None) is False
    _validate_startup_settings(settings)
