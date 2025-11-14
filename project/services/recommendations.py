"""Recommendation engine for cashback optimization."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .categories import CategoryNormalizer
from .db import AsyncDatabase


@dataclass(frozen=True)
class Recommendation:
    title: str
    details: str
    context: Dict[str, str]


class RecommendationService:
    """High-level recommendation helpers."""

    def __init__(self, db: AsyncDatabase, normalizer: CategoryNormalizer) -> None:
        self._db = db
        self._normalizer = normalizer

    async def recommend_best_card_for(self, user_id: int, category: str) -> Optional[Recommendation]:
        normalized = self._normalizer.normalize(category)
        categories = await self._db.fetch_all_category_rates(user_id)
        best: Optional[dict[str, Any]] = None
        for entry in categories:
            if self._normalizer.normalize(entry["normalized_name"]) != normalized:
                continue
            if best is None or entry["cashback_rate"] > best["cashback_rate"]:
                best = entry
        if not best:
            return None
        return Recommendation(
            title="best_card",
            details=str(best["bank_name"]),
            context={
                "category": normalized,
                "rate": f"{float(best['cashback_rate']) * 100:.1f}%",
            },
        )

    async def recommend_what_to_update(self, user_id: int, bank_id: int) -> List[Recommendation]:
        categories = await self._db.fetch_all_category_rates(user_id)
        weak: List[Recommendation] = []
        for entry in categories:
            if entry["user_bank_id"] != bank_id:
                continue
            rate = float(entry["cashback_rate"])
            if rate < 0.01:
                weak.append(
                    Recommendation(
                        title="update_category",
                        details=entry["name"],
                        context={"rate": f"{rate * 100:.1f}%"},
                    )
                )
        return weak

    async def recommend_where_to_move_cashback(self, user_id: int) -> Optional[Recommendation]:
        categories = await self._db.fetch_all_category_rates(user_id)
        if not categories:
            return None
        best = max(categories, key=lambda entry: entry["cashback_rate"])
        return Recommendation(
            title="move_cashback",
            details=best["bank_name"],
            context={
                "category": best["name"],
                "rate": f"{float(best['cashback_rate']) * 100:.1f}%",
            },
        )

    async def recommend_new_category_opportunities(self, user_id: int) -> List[Recommendation]:
        categories = await self._db.fetch_all_category_rates(user_id)
        coverage: Dict[str, float] = defaultdict(float)
        for entry in categories:
            normalized = self._normalizer.normalize(entry["normalized_name"])
            coverage[normalized] = max(coverage[normalized], float(entry["cashback_rate"]))
        opportunities: List[Recommendation] = []
        for category, rate in coverage.items():
            if rate < 0.02:
                opportunities.append(
                    Recommendation(
                        title="new_opportunity",
                        details=category,
                        context={"rate": f"{rate * 100:.1f}%"},
                    )
                )
        return opportunities

