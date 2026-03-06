from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DraftCashbackItem(BaseModel):
    raw_category: str
    normalized_category: str
    percent: Decimal = Field(..., ge=0, le=100)
    source_type: str


class CashbackItemRead(DraftCashbackItem):
    id: int
    display_category: str


class DeleteIntent(BaseModel):
    kind: Literal["bank", "category"]
    target: str


class BestQueryIntent(BaseModel):
    raw_category: str
    normalized_category: str


class RankingEntry(BaseModel):
    bank_id: int
    bank_name: str
    normalized_category: str
    percent: Decimal


class CategoryLeader(BaseModel):
    category_slug: str
    category_name: str
    best_percent: Decimal
    bank_names: list[str]


class BankScore(BaseModel):
    bank_name: str
    score: int
