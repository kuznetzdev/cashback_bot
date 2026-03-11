from __future__ import annotations

import re

from app.domain.errors import ValidationError


USERNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,30}[a-z0-9])?$")


def normalize_username(raw_username: str) -> str:
    username = raw_username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError("errors.invalid_username")
    return username


def normalize_email(raw_email: str | None) -> str | None:
    if raw_email is None:
        return None
    email = raw_email.strip().lower()
    if not email:
        return None
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValidationError("errors.invalid_email")
    return email
