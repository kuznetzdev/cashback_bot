from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class BankCategory(BaseModel):
    name: str
    rate: float = Field(ge=0, description="Cashback percent as numeric value (e.g., 5 for 5%).")
    merged_from: Optional[List[str]] = None
    deleted: bool = False


class Bank(BaseModel):
    id: Optional[int] = None
    user_id: int
    name: str
    categories: List[BankCategory] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def active_categories(self) -> List[BankCategory]:
        return [category for category in self.categories if not category.deleted]
