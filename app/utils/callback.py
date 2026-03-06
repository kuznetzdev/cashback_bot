from __future__ import annotations

from app.core.constants import CALLBACK_PREFIX


def nav(*parts: object) -> str:
    return ":".join([CALLBACK_PREFIX, *[str(part) for part in parts]])


def split_nav(value: str) -> list[str]:
    parts = value.split(":")
    if not parts or parts[0] != CALLBACK_PREFIX:
        return []
    return parts[1:]
