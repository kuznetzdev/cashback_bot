from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.domain.models import BankScore, CategoryLeader
from app.domain.services.categories import CategoryService


@dataclass(slots=True)
class RankingEntry:
    bank_id: int
    bank_name: str
    category_slug: str
    percent: Decimal


class RankingService:
    def __init__(self, categories: CategoryService) -> None:
        self.categories = categories

    def top_by_category(self, entries: list[RankingEntry], language: str) -> list[CategoryLeader]:
        grouped: dict[str, list[RankingEntry]] = defaultdict(list)
        for entry in entries:
            grouped[entry.category_slug].append(entry)
        leaders: list[CategoryLeader] = []
        for slug, group in grouped.items():
            best_percent = max(item.percent for item in group)
            bank_names = sorted({item.bank_name for item in group if item.percent == best_percent})
            leaders.append(
                CategoryLeader(
                    category_slug=slug,
                    category_name=self.categories.display_name(slug, language),
                    best_percent=best_percent,
                    bank_names=bank_names,
                )
            )
        return sorted(leaders, key=lambda item: item.category_name.lower())

    def top_global(self, entries: list[RankingEntry], language: str = "en") -> list[BankScore]:
        scores: dict[str, int] = defaultdict(int)
        for leader in self.top_by_category(entries, language):
            for bank_name in leader.bank_names:
                scores[bank_name] += 1
        result = [BankScore(bank_name=bank_name, score=score) for bank_name, score in scores.items()]
        return sorted(result, key=lambda item: (-item.score, item.bank_name.lower()))

    def best_for_slug(self, entries: list[RankingEntry], slug: str, language: str) -> CategoryLeader | None:
        target_slugs = self.categories.expand_query_slugs(slug)
        filtered = [entry for entry in entries if entry.category_slug in target_slugs]
        if not filtered:
            return None
        best = max(entry.percent for entry in filtered)
        banks = sorted({entry.bank_name for entry in filtered if entry.percent == best})
        return CategoryLeader(
            category_slug=slug,
            category_name=self.categories.display_name(slug, language),
            best_percent=best,
            bank_names=banks,
        )
