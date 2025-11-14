"""Analytics ranking helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class CategorySummary:
    category: str
    total_amount: float
    total_cashback: float

    @property
    def cashback_rate(self) -> float:
        if self.total_amount == 0:
            return 0.0
        return self.total_cashback / self.total_amount


class RankingService:
    """Build simple rankings of categories by cashback."""

    def build_category_ranking(
        self, summaries: Iterable[tuple[str, float, float]], limit: int = 5
    ) -> List[CategorySummary]:
        top = []
        for category, total_amount, total_cashback in summaries:
            top.append(CategorySummary(category, total_amount, total_cashback))
        top.sort(key=lambda summary: summary.total_cashback, reverse=True)
        return top[:limit]
