"""NLP service supporting categorisation and recommendations."""
from __future__ import annotations

from typing import Dict, List


class NlpService:
    """Extracts entities and intents from OCR text."""

    def extract_entities(self, text: str) -> Dict[str, object]:
        merchants = ["Supermarket", "Online Store"]
        if "Bonus" in text:
            merchants.append("Loyalty Program")
        return {"merchants": merchants, "keywords": text.lower().split()}

    def detect_intent(self, text: str) -> str:
        if "bonus" in text.lower():
            return "reward"
        return "purchase"

    def recommend_templates(self, text: str) -> List[str]:
        if "total" in text.lower():
            return ["total_amount", "cashback_candidate"]
        return []


__all__ = ["NlpService"]
