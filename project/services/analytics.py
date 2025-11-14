"""Advanced analytics for cashback categories."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from .categories import CategoryNormalizer
from .db import AsyncDatabase


@dataclass(frozen=True)
class CategoryInsight:
    bank_name: str
    category: str
    normalized_category: str
    rate: float
    level: int


@dataclass(frozen=True)
class BankStrength:
    bank_name: str
    score: int
    top_categories: int
    weak_categories: int


class AnalyticsService:
    """PRO analytics helpers for the bot."""

    def __init__(self, db: AsyncDatabase, normalizer: CategoryNormalizer) -> None:
        self._db = db
        self._normalizer = normalizer

    async def _collect_insights(self, user_id: int) -> List[CategoryInsight]:
        rows = await self._db.fetch_all_category_rates(user_id)
        insights: List[CategoryInsight] = []
        for row in rows:
            normalized = self._normalizer.normalize(row["normalized_name"])
            insights.append(
                CategoryInsight(
                    bank_name=row["bank_name"],
                    category=row["name"],
                    normalized_category=normalized,
                    rate=float(row["cashback_rate"]),
                    level=int(row["level"]),
                )
            )
        return insights

    async def top_worst_categories(self, user_id: int, limit: int = 5) -> List[CategoryInsight]:
        insights = await self._collect_insights(user_id)
        insights.sort(key=lambda insight: insight.rate)
        return insights[:limit]

    async def top_by_buckets(self, user_id: int) -> Dict[str, List[CategoryInsight]]:
        insights = await self._collect_insights(user_id)
        buckets: Dict[str, List[CategoryInsight]] = defaultdict(list)
        for insight in insights:
            rate_percent = insight.rate * 100
            if rate_percent >= 10:
                bucket = "10-100%"
            elif rate_percent >= 5:
                bucket = "5-9%"
            elif rate_percent >= 1:
                bucket = "1-4%"
            else:
                bucket = "0%"
            buckets[bucket].append(insight)
        for key in buckets:
            buckets[key].sort(key=lambda insight: insight.rate, reverse=True)
        return buckets

    async def bank_strength_score(self, user_id: int) -> List[BankStrength]:
        insights = await self._collect_insights(user_id)
        top_threshold = 0.05
        weak_threshold = 0.01
        per_bank_top: Dict[str, int] = defaultdict(int)
        per_bank_weak: Dict[str, int] = defaultdict(int)
        for insight in insights:
            if insight.rate >= top_threshold:
                per_bank_top[insight.bank_name] += 1
            if insight.rate < weak_threshold:
                per_bank_weak[insight.bank_name] += 1
        strengths: List[BankStrength] = []
        for bank_name in {insight.bank_name for insight in insights}:
            top_count = per_bank_top.get(bank_name, 0)
            weak_count = per_bank_weak.get(bank_name, 0)
            score = top_count * 2 - weak_count
            strengths.append(
                BankStrength(
                    bank_name=bank_name,
                    score=score,
                    top_categories=top_count,
                    weak_categories=weak_count,
                )
            )
        strengths.sort(key=lambda strength: strength.score, reverse=True)
        return strengths

