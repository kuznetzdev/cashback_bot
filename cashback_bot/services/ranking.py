from __future__ import annotations

"""Bank ranking and analytics."""
from collections import defaultdict
from typing import Dict, List, Tuple

from ..models.item import CashbackItem


class RankingService:
    def _group_by_bank(self, items: List[CashbackItem]) -> Dict[str, List[CashbackItem]]:
        grouped: Dict[str, List[CashbackItem]] = defaultdict(list)
        for item in items:
            grouped[item.bank].append(item)
        return grouped

    def best_overall_bank(self, items: List[CashbackItem]) -> Tuple[str, float]:
        grouped = self._group_by_bank(items)
        best_bank = ""
        best_rate = -1.0
        for bank, bank_items in grouped.items():
            rate = sum(item.rate for item in bank_items)
            if rate > best_rate:
                best_bank = bank
                best_rate = rate
        return best_bank, best_rate

    def best_by_total_percent(self, items: List[CashbackItem]) -> Tuple[str, float]:
        grouped = self._group_by_bank(items)
        best_bank = ""
        best_sum = -1.0
        for bank, bank_items in grouped.items():
            total = sum(item.rate for item in bank_items)
            if total > best_sum:
                best_bank = bank
                best_sum = total
        return best_bank, best_sum

    def missing_categories(self, items: List[CashbackItem], desired: List[str]) -> List[str]:
        existing = {item.normalized_category() for item in items}
        return [category for category in desired if category.lower() not in existing]

    def highlight_gaps(self, items: List[CashbackItem], threshold: float = 3.0) -> List[str]:
        grouped = self._group_by_bank(items)
        categories: Dict[str, List[float]] = defaultdict(list)
        for bank_items in grouped.values():
            for item in bank_items:
                categories[item.normalized_category()].append(item.rate)
        alerts = []
        for category, rates in categories.items():
            if not rates:
                continue
            if max(rates) - min(rates) >= threshold:
                alerts.append(category)
        return alerts

    def suggestions(self, items: List[CashbackItem]) -> List[str]:
        grouped = self._group_by_bank(items)
        suggestions: List[str] = []
        for category, rates in self._category_rates(items).items():
            best_rate = max(rates)
            for bank, bank_items in grouped.items():
                bank_rate = next((it.rate for it in bank_items if it.normalized_category() == category), 0.0)
                if bank_rate + 0.1 < best_rate:
                    suggestions.append(
                        f"Переключите карту: банк {bank} уступает в категории {category} ({bank_rate:.1f}% < {best_rate:.1f}%)"
                    )
        return suggestions

    def _category_rates(self, items: List[CashbackItem]) -> Dict[str, List[float]]:
        categories: Dict[str, List[float]] = defaultdict(list)
        for item in items:
            categories[item.normalized_category()].append(item.rate)
        return categories
