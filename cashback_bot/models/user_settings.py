from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    user_id: int
    locale: str = "ru"
    daily_notifications: bool = True
    monthly_notifications: bool = True
    timezone: str = "UTC"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    best_preferences: Optional[list[str]] = None
