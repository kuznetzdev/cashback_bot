"""Regression tests that pin category normalization and parsing against the
raw strings observed on real bank-app screenshots.

Every entry below is the exact `raw_category` text seen in a screenshot, paired
with the canonical slug the rest of the app must map it to. Adding new
screenshots to the product should add entries here — the parser/category
service is allowed to evolve, but these mappings must stay stable so downstream
ranking keeps grouping correctly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService

# (raw_category_text, expected_slug) — sourced from 11 real/representative
# screenshots: T-Bank April, T-Bank "В Городе", SberPrime, Yandex Plus, MTS,
# VTB, MTS WEEKEND, plus 4 synthetic bank UIs (Город Банк, Нова Банк, Орбита
# Банк, Север Банк) modelled on how Russian bank apps actually render
# cashback tiles in 2025.
SCREENSHOT_CATEGORY_CASES: list[tuple[str, str]] = [
    # T-Bank April
    ("Дом и ремонт", "home_goods"),
    ("Одежда и обувь", "clothing"),
    ("Отели", "hotels"),
    ("Фастфуд", "fast_food"),
    # T-Bank "В Городе" — qualifier stripped by normalizer
    ("Супермаркеты в Городе", "supermarkets"),
    ("Шопинг в Городе", "shopping"),
    ("Спорттовары", "sports"),
    # SberPrime
    ("На все покупки", "all_purchases"),
    ("Аптеки", "pharmacy"),
    ("Кафе и рестораны", "restaurants"),
    ("Транспорт", "transport"),
    ("Хобби и развлечения", "entertainment"),
    # Yandex Plus
    ("Супермаркеты", "supermarkets"),
    ("Кафе, бары и рестораны", "restaurants"),
    # MTS
    ("Оплата связи МТС", "telecom"),
    ("Топливо и АЗС", "fuel"),
    ("Рестораны", "restaurants"),
    # VTB
    ("Ж/д билеты", "railway"),
    ("Автоуслуги", "auto_services"),
    # MTS WEEKEND
    ("в супермаркетах", "supermarkets"),
    ("Рестораны и доставка еды", "restaurants"),
    ("Кино", "movies"),
    ("Такси и каршеринг", "transport"),
    ("Театры и концерты", "theatre"),
    ("Книги", "books"),
    ("за всё", "all_purchases"),
    # Город Банк — "Повышенный кэшбэк" (select 3 of 5)
    ("Маркетплейсы", "marketplaces"),
    ("Развлечения", "entertainment"),
    ("Одежда", "clothing"),
    ("Путешествия", "travel"),
    # Нова Банк — "Ваш кэшбэк на май"
    ("Онлайн-покупки", "marketplaces"),
    ("Маркетплейсы и интернет-магазины", "marketplaces"),
    ("Красота", "beauty"),
    ("Салоны красоты и косметика", "beauty"),
    # Орбита Банк — "Любимые категории"
    ("Продукты", "supermarkets"),
    ("Детские товары", "children_goods"),
    ("АЗС", "fuel"),
    ("Электроника", "electronics"),
    # Север Банк — "Категории кэшбэка"
    ("Продукты и товары для дома", "supermarkets"),
    ("Топливо и автосервисы", "fuel"),
    ("Лекарства и товары для здоровья", "pharmacy"),
    ("Такси", "transport"),
    ("Кафе и рестораны", "restaurants"),
]


@pytest.fixture(scope="module")
def categories() -> CategoryService:
    return CategoryService()


@pytest.mark.parametrize(("raw", "expected_slug"), SCREENSHOT_CATEGORY_CASES)
def test_category_normalization_matches_screenshot(
    categories: CategoryService, raw: str, expected_slug: str
) -> None:
    assert categories.normalize(raw).slug == expected_slug, (
        f"Expected '{raw}' to normalize to '{expected_slug}'"
    )


@pytest.mark.parametrize(("raw", "expected_slug"), SCREENSHOT_CATEGORY_CASES)
def test_parser_consumes_screenshot_lines(categories: CategoryService, raw: str, expected_slug: str) -> None:
    parser = ParserService(categories)
    # The OCR adapter emits one "Category: N%" line per offer. Verify the parser
    # turns each real screenshot line into exactly one draft item with the
    # expected normalized slug and percent.
    items = parser.parse_ocr_text(f"{raw}: 5%")
    assert len(items) == 1, f"Expected exactly 1 parsed item for '{raw}', got {len(items)}"
    assert items[0].normalized_category == expected_slug
    assert items[0].percent == Decimal("5.00")


def test_parser_handles_mixed_screenshot_block(categories: CategoryService) -> None:
    parser = ParserService(categories)
    # Simulate the MTS screenshot: base cashback, then category lines.
    text = "\n".join(
        [
            "Оплата связи МТС: 30%",
            "Дом и ремонт: 5%",
            "Топливо и АЗС: 5%",
            "Отели: 5%",
            "Рестораны: 5%",
        ]
    )
    items = parser.parse_ocr_text(text)
    slugs = {item.normalized_category for item in items}
    # Each of the 5 mapped to a distinct canonical slug.
    assert slugs == {"telecom", "home_goods", "fuel", "hotels", "restaurants"}
    # Highest percent wins in dedup (none collide here, so all stay).
    assert len(items) == 5


def test_parser_drops_section_headers_gracefully(categories: CategoryService) -> None:
    parser = ParserService(categories)
    # ParserService is fed text that might include leftover headers if OCR
    # fails. Lines without a percent should be silently skipped — not raise.
    text = "\n".join(
        [
            "Категории в апреле",
            "5% Дом и ремонт",
            "Условия программы лояльности",
            "5% Рестораны",
            "Проводим техработы до 1:00",
        ]
    )
    items = parser.parse_ocr_text(text)
    slugs = {item.normalized_category for item in items}
    assert slugs == {"home_goods", "restaurants"}


@pytest.mark.parametrize(
    ("query", "expected_slug"),
    [
        ("бензин", "fuel"),
        ("где лучше азс", "fuel"),
        ("кафе", "restaurants"),
        ("такси", "transport"),
        ("поезд", "railway"),
        ("театр", "theatre"),
        ("кино", "movies"),
        ("книга", "books"),
        ("отели", "hotels"),
        ("за всё", "all_purchases"),
        ("1% на все покупки", "all_purchases"),
    ],
)
def test_user_query_normalization(categories: CategoryService, query: str, expected_slug: str) -> None:
    assert categories.normalize(query).slug == expected_slug


def test_fuzzy_typos_still_resolve(categories: CategoryService) -> None:
    # Typo resilience — rapidfuzz at score_cutoff=80 should catch most single-char typos.
    assert categories.normalize("рестораы").slug == "restaurants"
    assert categories.normalize("супермаркет").slug == "supermarkets"
    assert categories.normalize("апткеи").slug == "pharmacy"


def test_unknown_category_falls_back_to_slugified(categories: CategoryService) -> None:
    # Truly unknown categories (rare bank offers like a specific merchant name)
    # must not crash — they fall back to a slug built from the raw text.
    normalized = categories.normalize("Tasty Coffee")
    assert normalized.slug  # non-empty, not "other"
    assert normalized.slug == "tasty_coffee"
