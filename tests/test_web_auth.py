from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from app.adapters.auth_telegram.verifier import verify_telegram_login
from app.application.auth.normalization import normalize_username
from app.domain.errors import ValidationError


def _sign_payload(payload: dict[str, str], bot_token: str) -> dict[str, str]:
    lines = [f"{key}={payload[key]}" for key in sorted(payload)]
    data_check_string = "\n".join(lines)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    signed = dict(payload)
    signed["hash"] = signature
    return signed


def test_verify_telegram_login_success() -> None:
    bot_token = "123456:valid_token"
    payload = {
        "id": "42",
        "username": "demo_user",
        "first_name": "Demo",
        "last_name": "User",
        "auth_date": str(int(time.time())),
    }
    signed = _sign_payload(payload, bot_token)
    auth = verify_telegram_login(signed, bot_token=bot_token, max_age_seconds=60)
    assert auth.provider == "telegram"
    assert auth.provider_user_id == "42"
    assert auth.provider_username == "demo_user"
    assert auth.provider_display_name == "Demo User"


def test_verify_telegram_login_expired() -> None:
    bot_token = "123456:valid_token"
    payload = {
        "id": "42",
        "first_name": "Demo",
        "auth_date": str(int(time.time()) - 3600),
    }
    signed = _sign_payload(payload, bot_token)
    with pytest.raises(ValidationError) as error:
        verify_telegram_login(signed, bot_token=bot_token, max_age_seconds=30)
    assert error.value.message_key == "errors.auth_expired"


def test_normalize_username_is_lowercase_and_strips_spacing() -> None:
    assert normalize_username("  Demo.User  ") == "demo.user"


def test_normalize_username_rejects_invalid_symbols() -> None:
    with pytest.raises(ValidationError) as error:
        normalize_username("bad user!")
    assert error.value.message_key == "errors.invalid_username"
