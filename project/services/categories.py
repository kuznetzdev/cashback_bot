"""Category normalization utilities."""
from __future__ import annotations

import logging
from typing import Dict

LOGGER = logging.getLogger(__name__)


class CategoryNormalizer:
    """Normalize categories into unified forms."""

    def __init__(self) -> None:
        self._mapping: Dict[str, str] = {
            "groceries": "groceries",
            "food": "groceries",
            "supermarket": "groceries",
            "supermarkets": "groceries",
            "супермаркет": "groceries",
            "магазин": "groceries",
            "аптека": "pharmacy",
            "pharmacy": "pharmacy",
            "drugstore": "pharmacy",
            "restaurant": "dining",
            "dining": "dining",
            "кафе": "dining",
            "рестораны": "dining",
            "travel": "travel",
            "flight": "travel",
            "hotel": "travel",
            "отели": "travel",
            "путешествия": "travel",
            "gas": "transport",
            "taxi": "transport",
            "uber": "transport",
            "fuel": "transport",
            "азс": "transport",
            "electronics": "electronics",
            "tech": "electronics",
            "интернет": "online",
            "online": "online",
            "digital": "online",
            "entertainment": "entertainment",
            "развлечения": "entertainment",
            "education": "education",
            "образование": "education",
        }

    def normalize(self, category: str) -> str:
        key = category.strip().lower()
        normalized = self._mapping.get(key, key)
        LOGGER.debug("Normalized category '%s' -> '%s'", category, normalized)
        return normalized

    def decompose(self, category: str) -> list[str]:
        parts = [part.strip() for part in category.split("/") if part.strip()]
        return [self.normalize(part) for part in parts] or [self.normalize(category)]
