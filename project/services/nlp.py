"""NLP service for intent and entity extraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ParsedTransaction:
    amount: float
    category: str
    description: str


class NLPService:
    def parse_lines(self, lines: List[str]) -> List[ParsedTransaction]:
        transactions: List[ParsedTransaction] = []
        for line in lines:
            amount = self._extract_amount(line)
            if amount is None:
                continue
            category = self._detect_category(line)
            transactions.append(
                ParsedTransaction(amount=amount, category=category, description=line)
            )
        return transactions

    def _extract_amount(self, text: str) -> float | None:
        digits = "".join(ch if ch.isdigit() or ch == "." else " " for ch in text).split()
        for token in digits:
            try:
                return float(token)
            except ValueError:
                continue
        return None

    def _detect_category(self, text: str) -> str:
        lowered = text.lower()
        if "кафе" in lowered or "coffee" in lowered:
            return "coffee"
        if "аптека" in lowered:
            return "pharmacy"
        if "супермаркет" in lowered or "market" in lowered:
            return "groceries"
        return "other"
