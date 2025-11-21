from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class CashbackItem(BaseModel):
    category: str
    rate: float = Field(ge=0)
    bank: str
    source: str = Field(default="manual")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    quality: float = Field(default=1.0)

    def normalized_category(self) -> str:
        return self.category.strip().lower()
