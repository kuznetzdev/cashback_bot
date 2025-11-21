from __future__ import annotations

"""Parses OCR/plain text into structured cashback categories."""
import re
from typing import Iterable, List

from ..models.item import CashbackItem
from ..models.parsed_result import ParsedResult


class ParserService:
    CATEGORY_PATTERN = re.compile(r"(?P<name>[\w\sА-Яа-яёЁ&]+)\s*[-:]*\s*(?P<rate>\d+[\.,]?\d*)\s*%")

    def parse(self, text: str, *, bank: str, source: str = "ocr") -> ParsedResult:
        categories: List[CashbackItem] = []
        for match in self.CATEGORY_PATTERN.finditer(text):
            name = match.group("name").strip()
            rate = float(match.group("rate").replace(",", "."))
            categories.append(CashbackItem(category=name, rate=rate, bank=bank, source=source))
        if not categories:
            fallback = self._parse_lines(text.splitlines(), bank=bank, source=source)
            categories.extend(fallback)
        return ParsedResult(text=text, categories=categories, quality=1.0 if categories else 0.0)

    def _parse_lines(self, lines: Iterable[str], *, bank: str, source: str) -> List[CashbackItem]:
        items: List[CashbackItem] = []
        for raw in lines:
            parts = re.split(r"-|:", raw)
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            rate_part = parts[1].strip().replace("%", "").replace(",", ".")
            try:
                rate = float(rate_part)
            except ValueError:
                continue
            items.append(CashbackItem(category=name, rate=rate, bank=bank, source=source))
        return items
