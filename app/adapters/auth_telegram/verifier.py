from __future__ import annotations

import hashlib
import hmac
import time
from typing import Mapping

from app.application.auth.models import ExternalIdentityContext
from app.domain.errors import ValidationError


def verify_telegram_login(
    payload: Mapping[str, str],
    *,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> ExternalIdentityContext:
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

    provider_user_id = payload.get("id")
    if not provider_user_id:
        raise ValidationError("errors.invalid_auth")

    username = payload.get("username")
    first_name = payload.get("first_name", "").strip()
    last_name = payload.get("last_name", "").strip()
    display_name = " ".join(part for part in (first_name, last_name) if part).strip() or None
    return ExternalIdentityContext(
        provider="telegram",
        provider_user_id=provider_user_id,
        provider_username=username,
        provider_display_name=display_name,
    )


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
