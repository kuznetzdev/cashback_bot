"""OCR service abstractions for receipt processing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class OcrResult:
    text: str
    confidence: float
    items: List[Dict[str, object]]


class OcrService:
    """Simulates OCR modes used by the bot."""

    def recognise(self, image: bytes, mode: str = "smart") -> OcrResult:
        """Recognise receipt text.

        The *smart* mode increases the confidence to emulate more expensive OCR
        pipelines. The output is deterministic to keep tests reproducible.
        """

        base_text = "Total: 1234"
        base_items = [{"name": "Purchase", "amount": 1234.0}]
        if mode == "smart":
            confidence = 0.95
            items = base_items + [{"name": "Bonus", "amount": 120.0}]
        else:
            confidence = 0.8
            items = base_items
        return OcrResult(text=base_text, confidence=confidence, items=items)


__all__ = ["OcrService", "OcrResult"]
