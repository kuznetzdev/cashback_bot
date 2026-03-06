from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.schemas.cashback_item import BankScore, CategoryLeader, RankingEntry
from app.services.categories import CategoryService


class RankingService:
    def __init__(self, category_service: CategoryService) -> None:
        self.category_service = category_service

    def top_by_category(self, entries: list[RankingEntry], language: str) -> list[CategoryLeader]:
        grouped: dict[str, list[RankingEntry]] = defaultdict(list)
        for entry in entries:
            grouped[entry.normalized_category].append(entry)

        leaders: list[CategoryLeader] = []
        for slug, category_entries in grouped.items():
            best_percent = max(entry.percent for entry in category_entries)
            bank_names = sorted({entry.bank_name for entry in category_entries if entry.percent == best_percent})
            leaders.append(
                CategoryLeader(
                    category_slug=slug,
                    category_name=self.category_service.display_name(slug, language),
                    best_percent=best_percent,
                    bank_names=bank_names,
                )
            )
        return sorted(leaders, key=lambda item: item.category_name.lower())

    def top_by_bank(self, entries: list[RankingEntry], language: str) -> dict[str, list[tuple[str, Decimal]]]:
        grouped: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
        for entry in entries:
            grouped[entry.bank_name].append(
                (self.category_service.display_name(entry.normalized_category, language), entry.percent)
            )
        for bank_name, items in grouped.items():
            items.sort(key=lambda item: (-item[1], item[0].lower()))
        return dict(sorted(grouped.items(), key=lambda item: item[0].lower()))

    def top_global(self, entries: list[RankingEntry]) -> list[BankScore]:
        scores: dict[str, int] = defaultdict(int)
        for leader in self.top_by_category(entries, language="ru"):
            for bank_name in leader.bank_names:
                scores[bank_name] += 1
        result = [BankScore(bank_name=bank_name, score=score) for bank_name, score in scores.items()]
        return sorted(result, key=lambda item: (-item.score, item.bank_name.lower()))

    def best_for_query(self, entries: list[RankingEntry], query_slug: str, language: str) -> CategoryLeader | None:
        matched_slugs = self.category_service.expand_query_slugs(query_slug)
        relevant = [entry for entry in entries if entry.normalized_category in matched_slugs]
        if not relevant:
            return None
        best_percent = max(entry.percent for entry in relevant)
        bank_names = sorted({entry.bank_name for entry in relevant if entry.percent == best_percent})
        return CategoryLeader(
            category_slug=query_slug,
            category_name=self.category_service.display_name(query_slug, language),
            best_percent=best_percent,
            bank_names=bank_names,
        )
