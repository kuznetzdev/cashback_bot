from __future__ import annotations

from pydantic import BaseModel, Field


class UserSettingsRead(BaseModel):
    language: str
    notifications_enabled: bool


class ScreenStateData(BaseModel):
    mode: str | None = None
    selected_bank_id: int | None = None
    selected_bank_name: str | None = None
    draft_items: list[dict] = Field(default_factory=list)
    editing_index: int | None = None
    last_screen_message_id: int | None = None
