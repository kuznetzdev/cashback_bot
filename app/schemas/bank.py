from __future__ import annotations

from pydantic import BaseModel

from app.schemas.cashback_item import CashbackItemRead


class BankRead(BaseModel):
    id: int
    bank_name: str


class BankDetails(BaseModel):
    id: int
    bank_name: str
    items: list[CashbackItemRead]
