from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.core.enums import SourceType
from app.core.exceptions import ValidationError
from app.schemas.cashback_item import BestQueryIntent, DeleteIntent, DraftCashbackItem
from app.services.categories import CategoryService


class ParserService:
    _LINE_PATTERNS = [
        re.compile(r"^(?P<category>.+?)\s*[-:]\s*(?P<percent>\d{1,2}(?:[.,]\d{1,2})?)\s*%?$", re.IGNORECASE),
        re.compile(r"^(?P<category>.+?)\s+(?P<percent>\d{1,2}(?:[.,]\d{1,2})?)\s*%?$", re.IGNORECASE),
        re.compile(r"^(?P<percent>\d{1,2}(?:[.,]\d{1,2})?)\s*%?\s*(?:на|по|for)\s+(?P<category>.+?)$", re.IGNORECASE),
    ]

    _DELETE_BANK = re.compile(r"^(?:удали|удалить|delete)\s+(?:банк|bank)\s+(.+)$", re.IGNORECASE)
    _DELETE_CATEGORY = re.compile(
        r"^(?:удали|удалить|delete)\s+(?:категорию|категория|category)\s+(.+)$",
        re.IGNORECASE,
    )
    _BEST_PATTERNS = [
        re.compile(r"^(?:лучший\s+кэшбэк\s+на|где\s+лучше)\s+(.+)$", re.IGNORECASE),
        re.compile(r"^(?:best\s+cashback\s+for|where\s+is\s+better\s+for)\s+(.+)$", re.IGNORECASE),
    ]

    def __init__(self, category_service: CategoryService) -> None:
        self.category_service = category_service

    def parse_manual_lines(self, text: str) -> list[DraftCashbackItem]:
        items = self._parse_lines(text, SourceType.MANUAL.value)
        if not items:
            raise ValidationError("errors.invalid_manual_input")
        return items

    def parse_ocr_text(self, text: str) -> list[DraftCashbackItem]:
        return self._parse_lines(text, SourceType.OCR.value)

    def _parse_lines(self, text: str, source_type: str) -> list[DraftCashbackItem]:
        best_by_slug: dict[str, DraftCashbackItem] = {}
        for line in text.splitlines():
            parsed = self._parse_line(line.strip())
            if parsed is None:
                continue
            raw_category, percent = parsed
            normalized = self.category_service.normalize(raw_category)
            item = DraftCashbackItem(
                raw_category=raw_category,
                normalized_category=normalized.slug,
                percent=percent,
                source_type=source_type,
            )
            current = best_by_slug.get(item.normalized_category)
            if current is None or item.percent > current.percent:
                best_by_slug[item.normalized_category] = item
        return sorted(best_by_slug.values(), key=lambda item: (-item.percent, item.raw_category.lower()))

    def _parse_line(self, line: str) -> tuple[str, Decimal] | None:
        if not line:
            return None
        for pattern in self._LINE_PATTERNS:
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
        bank_match = self._DELETE_BANK.match(stripped)
        if bank_match:
            return DeleteIntent(kind="bank", target=bank_match.group(1).strip())
        category_match = self._DELETE_CATEGORY.match(stripped)
        if category_match:
            return DeleteIntent(kind="category", target=category_match.group(1).strip())
        return None

    def understand_best_query(self, text: str) -> BestQueryIntent | None:
        stripped = text.strip()
        for pattern in self._BEST_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            raw_category = match.group(1).strip()
            normalized = self.category_service.normalize(raw_category)
            return BestQueryIntent(
                raw_category=raw_category,
                normalized_category=normalized.slug,
            )
        return None
