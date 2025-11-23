from __future__ import annotations

from typing import List
from pydantic import BaseModel

from .item import CashbackItem


class ParsedResult(BaseModel):
    text: str
    categories: List[CashbackItem]
    quality: float = 1.0
