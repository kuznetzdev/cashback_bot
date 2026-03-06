from __future__ import annotations

from pydantic import BaseModel


class UserRead(BaseModel):
    id: int
    telegram_user_id: int
    username: str | None = None
    full_name: str | None = None
    language: str
    notifications_enabled: bool
