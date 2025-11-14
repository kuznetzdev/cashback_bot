"""Category detection logic for parsed transactions."""
from __future__ import annotations

from typing import Dict


class CategoryService:
    """Maps merchants to human readable categories."""

    CATEGORY_MAP = {
        "supermarket": "Продукты",
        "online": "Онлайн-покупки",
        "loyalty": "Бонусные программы",
    }

    def detect(self, merchant: str) -> str:
        key = merchant.lower()
        for prefix, category in self.CATEGORY_MAP.items():
            if prefix in key:
                return category
        return "Прочее"

    def enrich(self, ocr_items: Dict[str, object]) -> Dict[str, object]:
        merchant = ocr_items.get("name", "Unknown")
        category = self.detect(str(merchant))
        return {**ocr_items, "category": category}


__all__ = ["CategoryService"]
