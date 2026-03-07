from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Mapping

from app.domain.errors import ValidationError


@dataclass(slots=True)
class TelegramAuthData:
    telegram_id: int
    username: str | None
    full_name: str | None


def verify_telegram_login(payload: Mapping[str, str], *, bot_token: str, max_age_seconds: int = 86400) -> TelegramAuthData:
    provided_hash = payload.get("hash")
    if not provided_hash:
        raise ValidationError("errors.invalid_auth")

    auth_date_raw = payload.get("auth_date")
    if not auth_date_raw:
        raise ValidationError("errors.invalid_auth")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as error:
        raise ValidationError("errors.invalid_auth") from error
    if int(time.time()) - auth_date > max_age_seconds:
        raise ValidationError("errors.auth_expired")

    data_check_string = _build_data_check_string(payload)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash):
        raise ValidationError("errors.invalid_auth")

    raw_id = payload.get("id")
    if not raw_id:
        raise ValidationError("errors.invalid_auth")
    try:
        telegram_id = int(raw_id)
    except ValueError as error:
        raise ValidationError("errors.invalid_auth") from error

    username = payload.get("username")
    first_name = payload.get("first_name", "").strip()
    last_name = payload.get("last_name", "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip() or None
    return TelegramAuthData(telegram_id=telegram_id, username=username, full_name=full_name)


def _build_data_check_string(payload: Mapping[str, str]) -> str:
    pairs: list[str] = []
    for key in sorted(payload):
        if key == "hash":
            continue
        value = payload.get(key)
        if value is None:
            continue
        pairs.append(f"{key}={value}")
    return "\n".join(pairs)
