from __future__ import annotations

"""Category utilities: deduplication, merging, preview."""
from collections import defaultdict
from typing import Iterable, List

from ..models.bank import BankCategory


class CategoryService:
    def merge_duplicates(self, categories: Iterable[BankCategory]) -> List[BankCategory]:
        merged: dict[str, BankCategory] = {}
        synonyms = defaultdict(list)
        for category in categories:
            key = category.name.strip().lower()
            if key in merged:
                existing = merged[key]
                existing.rate = max(existing.rate, category.rate)
                source_names = existing.merged_from or [existing.name]
                source_names.append(category.name)
                existing.merged_from = list({*source_names})
                synonyms[key].append(category.name)
            else:
                merged[key] = category
        for key, names in synonyms.items():
            merged[key].merged_from = list({merged[key].name, *names})
        return list(merged.values())

    def preview(self, categories: Iterable[BankCategory]) -> str:
        lines = []
        for idx, category in enumerate(categories, start=1):
            lines.append(f"{idx}. {category.name} — {category.rate:.2f}%")
        return "\n".join(lines) if lines else "Нет категорий"

    def soft_delete(self, categories: List[BankCategory], name: str) -> List[BankCategory]:
        normalized = name.strip().lower()
        for category in categories:
            if category.name.strip().lower() == normalized:
                category.deleted = True
        return categories
