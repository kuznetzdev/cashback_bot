"""Analytics and ranking utilities."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .db import Achievement, Transaction


class RankingService:
    def summarize(self, transactions: Iterable[Transaction]) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for transaction in transactions:
            totals[transaction.category] = totals.get(transaction.category, 0.0) + transaction.amount
        return totals

    def build_achievements(self, totals: Dict[str, float]) -> List[Achievement]:
        achievements: List[Achievement] = []
        for category, amount in totals.items():
            if amount <= 0:
                continue
            progress = min(int(amount // 100 * 10), 100)
            achievements.append(
                Achievement(
                    code=f"{category}_hero",
                    title=f"Герой категории {category}",
                    progress=progress,
                )
            )
        return achievements
