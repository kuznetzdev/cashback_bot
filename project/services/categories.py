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
            "restaurant": "dining",
            "dining": "dining",
            "travel": "travel",
            "flight": "travel",
            "hotel": "travel",
            "gas": "transport",
            "taxi": "transport",
            "uber": "transport",
            "electronics": "electronics",
        }

    def normalize(self, category: str) -> str:
        key = category.strip().lower()
        normalized = self._mapping.get(key, key)
        LOGGER.debug("Normalized category '%s' -> '%s'", category, normalized)
        return normalized

    def decompose(self, category: str) -> list[str]:
        parts = [part.strip() for part in category.split("/") if part.strip()]
        return [self.normalize(part) for part in parts] or [self.normalize(category)]
