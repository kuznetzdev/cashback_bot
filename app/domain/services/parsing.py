from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.domain.enums import SourceType
from app.domain.errors import ValidationError
from app.domain.models import BestQueryIntent, CashbackDraftItem, DeleteIntent
from app.domain.services.categories import CategoryService


class ParserService:
    # Accept percent up to 3 digits so a legitimate 100% marketing promo
    # ("100% Cashback on first purchase") parses. The post-match guard in
    # ``_parse_line`` still caps out-of-range values (>100 or <=0).
    LINE_PATTERNS = [
        re.compile(r"^(?P<category>.+?)\s*[-:]\s*(?P<percent>\d{1,3}(?:[.,]\d{1,2})?)\s*%?$", re.IGNORECASE),
        # "N% Category" — the layout every Russian bank app uses on its cashback page.
        re.compile(r"^[+\-]?(?P<percent>\d{1,3}(?:[.,]\d{1,2})?)\s*%\s+(?P<category>.+?)$", re.IGNORECASE),
        re.compile(r"^(?P<category>.+?)\s+(?P<percent>\d{1,3}(?:[.,]\d{1,2})?)\s*%?$", re.IGNORECASE),
        re.compile(r"^(?P<percent>\d{1,3}(?:[.,]\d{1,2})?)\s*%?\s*(?:for|on)\s+(?P<category>.+?)$", re.IGNORECASE),
    ]
    DELETE_BANK = re.compile(r"^(?:удали|удалить|delete)\s+(?:банк|bank)\s+(.+)$", re.IGNORECASE)
    DELETE_CATEGORY = re.compile(r"^(?:удали|удалить|delete)\s+(?:категорию|категория|category)\s+(.+)$", re.IGNORECASE)
    BEST_PATTERNS = [
        re.compile(r"^(?:best\s+cashback\s+for|where\s+is\s+better\s+for)\s+(.+)$", re.IGNORECASE),
        re.compile(r"^(?:лучший\s+кэшбэк\s+на|где\s+лучше|что\s+лучше\s+для)\s+(.+)$", re.IGNORECASE),
    ]

    def __init__(self, categories: CategoryService) -> None:
        self.categories = categories

    def parse_manual_lines(self, text: str) -> list[CashbackDraftItem]:
        items = self._parse_lines(text, SourceType.MANUAL.value)
        if not items:
            raise ValidationError("errors.invalid_manual_input")
        return items

    def parse_ocr_text(self, text: str) -> list[CashbackDraftItem]:
        return self._parse_lines(text, SourceType.OCR.value)

    def _parse_lines(self, text: str, source_type: str) -> list[CashbackDraftItem]:
        best: dict[str, CashbackDraftItem] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed = self._parse_line(line)
            if parsed is None:
                continue
            category_raw, percent = parsed
            normalized = self.categories.normalize(category_raw)
            item = CashbackDraftItem(
                raw_category=category_raw,
                normalized_category=normalized.slug,
                percent=percent,
                source_type=source_type,
            )
            current = best.get(item.normalized_category)
            if current is None or item.percent > current.percent:
                best[item.normalized_category] = item
        return sorted(best.values(), key=lambda item: (-item.percent, item.raw_category.lower()))

    def _parse_line(self, line: str) -> tuple[str, Decimal] | None:
        for pattern in self.LINE_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            category = match.group("category").strip(" :-")
            percent_raw = match.group("percent").replace(",", ".")
            try:
                percent = Decimal(percent_raw)
            except InvalidOperation:
                return None
            if not category or percent <= 0 or percent > 100:
                return None
            return category, percent.quantize(Decimal("0.01"))
        return None

    def understand_delete_command(self, text: str) -> DeleteIntent | None:
        stripped = text.strip()
        bank_match = self.DELETE_BANK.match(stripped)
        if bank_match:
            return DeleteIntent(kind="bank", target=bank_match.group(1).strip())
        category_match = self.DELETE_CATEGORY.match(stripped)
        if category_match:
            return DeleteIntent(kind="category", target=category_match.group(1).strip())
        return None

    def understand_best_query(self, text: str) -> BestQueryIntent | None:
        stripped = text.strip()
        for pattern in self.BEST_PATTERNS:
            match = pattern.match(stripped)
            if match:
                return BestQueryIntent(normalized_category=self.categories.normalize(match.group(1).strip()).slug)
        return None
