from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import process

from app.core.constants import TEMPLATE_CATEGORY_SLUGS


@dataclass(slots=True)
class NormalizedCategory:
    slug: str
    display_ru: str
    display_en: str


class CategoryService:
    def __init__(self) -> None:
        self._definitions = {
            "fuel": {
                "ru": "АЗС",
                "en": "Fuel",
                "synonyms": ["азс", "заправка", "fuel", "fuel station", "gas", "gas station"],
                "related": [],
            },
            "restaurants": {
                "ru": "Рестораны",
                "en": "Restaurants",
                "synonyms": ["рестораны", "кафе", "еда", "food", "dining", "restaurants", "cafes"],
                "related": [],
            },
            "supermarkets": {
                "ru": "Супермаркеты",
                "en": "Supermarkets",
                "synonyms": ["супермаркеты", "продукты", "groceries", "supermarkets"],
                "related": ["groceries"],
            },
            "groceries": {
                "ru": "Продукты питания",
                "en": "Groceries",
                "synonyms": ["продукты питания", "grocery", "groceries"],
                "related": ["supermarkets"],
            },
            "pharmacy": {
                "ru": "Аптеки",
                "en": "Pharmacies",
                "synonyms": ["аптека", "аптеки", "pharmacy", "drugstore"],
                "related": [],
            },
            "movies": {
                "ru": "Кино",
                "en": "Movies",
                "synonyms": ["кино", "movies", "cinema"],
                "related": [],
            },
            "travel": {
                "ru": "Путешествия",
                "en": "Travel",
                "synonyms": ["путешествия", "travel", "trip", "tickets"],
                "related": [],
            },
            "home_goods": {
                "ru": "Товары для дома",
                "en": "Home goods",
                "synonyms": ["товары для дома", "дом", "home goods", "household"],
                "related": ["decor", "construction"],
            },
            "decor": {
                "ru": "Декор",
                "en": "Decor",
                "synonyms": ["декор", "decor"],
                "related": ["home_goods"],
            },
            "construction": {
                "ru": "Строительство",
                "en": "Construction",
                "synonyms": ["строительство", "ремонт", "construction", "repair"],
                "related": ["home_goods"],
            },
        }
        self._term_to_slug: dict[str, str] = {}
        for slug, definition in self._definitions.items():
            for term in [slug, definition["ru"], definition["en"], *definition["synonyms"]]:
                self._term_to_slug[self._normalize_text(term)] = slug

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _slugify(self, value: str) -> str:
        cleaned = re.sub(r"[^\w\s-]", "", self._normalize_text(value))
        return re.sub(r"[\s-]+", "_", cleaned).strip("_") or "other"

    def _build(self, slug: str) -> NormalizedCategory:
        definition = self._definitions.get(slug)
        if definition is None:
            title = slug.replace("_", " ").title()
            return NormalizedCategory(slug=slug, display_ru=title, display_en=title)
        return NormalizedCategory(slug=slug, display_ru=definition["ru"], display_en=definition["en"])

    def normalize(self, raw: str) -> NormalizedCategory:
        cleaned = self._normalize_text(raw)
        if cleaned in self._term_to_slug:
            return self._build(self._term_to_slug[cleaned])

        match = process.extractOne(cleaned, self._term_to_slug.keys(), score_cutoff=80)
        if match:
            return self._build(self._term_to_slug[match[0]])

        slug = self._slugify(raw)
        title = raw.strip().title()
        return NormalizedCategory(slug=slug, display_ru=title, display_en=title)

    def display_name(self, slug: str, language: str) -> str:
        category = self._build(slug)
        return category.display_en if language == "en" else category.display_ru

    def expand_query_slugs(self, raw_or_slug: str) -> set[str]:
        normalized = self.normalize(raw_or_slug)
        related = set(self._definitions.get(normalized.slug, {}).get("related", []))
        return {normalized.slug, *related}

    def template_slugs(self) -> list[str]:
        return list(TEMPLATE_CATEGORY_SLUGS)
