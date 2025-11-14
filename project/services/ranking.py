"""Ranking service powering PRO analytics."""
from __future__ import annotations

from typing import List, Tuple

from project.services.db import Transaction


class RankingService:
    """Builds ranked leaderboards for cashback performance."""

    def build_leaderboard(self, transactions: List[Transaction]) -> List[Tuple[str, float]]:
        leaderboard: List[Tuple[str, float]] = []
        by_category: dict[str, float] = {}
        for transaction in transactions:
            by_category.setdefault(transaction.category, 0.0)
            by_category[transaction.category] += transaction.amount
        for category, amount in sorted(by_category.items(), key=lambda item: item[1], reverse=True):
            leaderboard.append((category, round(amount, 2)))
        return leaderboard


__all__ = ["RankingService"]
