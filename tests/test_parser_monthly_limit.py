from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService


@pytest.fixture
def parser() -> ParserService:
    return ParserService(CategoryService())


def test_parser_extracts_simple_limit_in_parens(parser: ParserService) -> None:
    items = parser.parse_manual_lines("АЗС 5% (до 3000)")
    assert len(items) == 1
    assert items[0].percent == Decimal("5.00")
    assert items[0].monthly_limit == Decimal("3000.00")


def test_parser_extracts_limit_without_parens(parser: ParserService) -> None:
    items = parser.parse_manual_lines("АЗС 5% до 3000 ₽")
    assert items[0].monthly_limit == Decimal("3000.00")


def test_parser_extracts_limit_with_thousand_separator(parser: ParserService) -> None:
    items = parser.parse_manual_lines("АЗС 5% до 3 000 руб")
    assert items[0].monthly_limit == Decimal("3000.00")


def test_parser_extracts_decimal_limit(parser: ParserService) -> None:
    items = parser.parse_manual_lines("Рестораны 5% до 1500.50")
    assert items[0].monthly_limit == Decimal("1500.50")


def test_parser_extracts_short_form_limit(parser: ParserService) -> None:
    items = parser.parse_manual_lines("АЗС 5% (до 3к)")
    assert items[0].monthly_limit == Decimal("3000.00")


def test_parser_recognises_max_keyword(parser: ParserService) -> None:
    items = parser.parse_manual_lines("Restaurants 5% max 1500")
    assert items[0].monthly_limit == Decimal("1500.00")


def test_parser_keeps_none_when_no_limit_present(parser: ParserService) -> None:
    items = parser.parse_manual_lines("АЗС 5%")
    assert items[0].monthly_limit is None


def test_parser_does_not_crash_on_malformed_limit_suffix(parser: ParserService) -> None:
    # "до" without a parseable number doesn't match the limit regex, so the
    # line is left as-is. We use parse_ocr_text (which returns [] on no
    # match) rather than parse_manual_lines (which raises) — this test
    # is about robustness, not happy-path manual input.
    items = parser.parse_ocr_text("АЗС 5% (до)")
    if items:
        assert items[0].monthly_limit is None


def test_parser_caps_pathological_limit_to_none(parser: ParserService) -> None:
    # A "limit" of nearly a billion rubles is almost certainly an OCR
    # misread of a balance counter. The suffix is stripped so the percent
    # pattern still matches, but no limit is recorded.
    items = parser.parse_manual_lines("АЗС 5% до 999999999")
    assert len(items) == 1
    assert items[0].monthly_limit is None


def test_parser_strips_limit_from_residual_category(parser: ParserService) -> None:
    items = parser.parse_manual_lines("АЗС 5% (до 3000)")
    # The raw_category captured for display should be just "АЗС", not "АЗС (до 3000)".
    assert "до" not in items[0].raw_category
    assert "3000" not in items[0].raw_category
