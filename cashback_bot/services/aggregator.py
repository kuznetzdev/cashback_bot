from __future__ import annotations

"""Aggregates categories from OCR, manual input, and templates."""
from typing import Iterable, List

from ..models.bank import BankCategory
from ..models.item import CashbackItem


class AggregatorService:
    def combine(self, *sources: Iterable[CashbackItem]) -> List[BankCategory]:
        merged: List[BankCategory] = []
        for source in sources:
            for item in source:
                merged.append(BankCategory(name=item.category, rate=item.rate))
        return merged
