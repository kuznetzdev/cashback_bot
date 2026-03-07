from __future__ import annotations

import re

from rapidfuzz import process

from app.domain.models import NormalizedCategory


class CategoryService:
    def __init__(self) -> None:
        self._definitions = {
            "fuel": {
                "ru": "АЗС",
                "en": "Fuel",
                "synonyms": [
                    "азс",
                    "заправка",
                    "заправки",
                    "fuel",
                    "fuel station",
                    "gas",
                    "gas station",
                ],
                "related": [],
            },
            "restaurants": {
                "ru": "Рестораны",
                "en": "Restaurants",
                "synonyms": ["ресторан", "рестораны", "кафе", "food", "dining", "restaurant", "restaurants"],
                "related": [],
            },
            "supermarkets": {
                "ru": "Супермаркеты",
                "en": "Supermarkets",
                "synonyms": ["супермаркет", "супермаркеты", "продукты", "supermarket", "supermarkets", "groceries"],
                "related": ["groceries"],
            },
            "groceries": {
                "ru": "Продукты питания",
                "en": "Groceries",
                "synonyms": ["продукты питания", "продуктовый магазин", "grocery", "groceries", "food store"],
                "related": ["supermarkets"],
            },
            "pharmacy": {
                "ru": "Аптеки",
                "en": "Pharmacy",
                "synonyms": ["аптека", "аптеки", "pharmacy", "drugstore"],
                "related": [],
            },
            "movies": {
                "ru": "Кино",
                "en": "Movies",
                "synonyms": ["кино", "кинотеатр", "cinema", "movie", "movies"],
                "related": [],
            },
            "travel": {
                "ru": "Путешествия",
                "en": "Travel",
                "synonyms": ["путешествия", "поездки", "билеты", "travel", "trip", "tickets"],
                "related": [],
            },
            "home_goods": {
                "ru": "Товары для дома",
                "en": "Home goods",
                "synonyms": ["товары для дома", "для дома", "home goods", "home", "household"],
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
            terms = [slug, definition["ru"], definition["en"], *definition["synonyms"]]
            for term in terms:
                self._term_to_slug[self._normalize_text(term)] = slug
        self._term_to_slug["groceries"] = "supermarkets"
        self._term_to_slug["продукты"] = "supermarkets"
        self._term_to_slug["продукты питания"] = "supermarkets"

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _slugify(self, value: str) -> str:
        normalized = self._normalize_text(value)
        cleaned = re.sub(r"[^\w\s-]", "", normalized)
        return re.sub(r"[\s-]+", "_", cleaned).strip("_") or "other"

    def normalize(self, raw: str) -> NormalizedCategory:
        normalized_raw = self._normalize_text(raw)
        slug = self._term_to_slug.get(normalized_raw)
        if slug is None:
            fuzzy = process.extractOne(normalized_raw, self._term_to_slug.keys(), score_cutoff=80)
            if fuzzy:
                slug = self._term_to_slug[fuzzy[0]]
        if slug is None:
            title = raw.strip().title()
            return NormalizedCategory(slug=self._slugify(raw), display_ru=title, display_en=title)
        definition = self._definitions[slug]
        return NormalizedCategory(slug=slug, display_ru=definition["ru"], display_en=definition["en"])

    def display_name(self, slug: str, language: str) -> str:
        definition = self._definitions.get(slug)
        if definition is None:
            return slug.replace("_", " ").title()
        return definition["en"] if language == "en" else definition["ru"]

    def expand_query_slugs(self, value: str) -> set[str]:
        normalized = self.normalize(value)
        related = set(self._definitions.get(normalized.slug, {}).get("related", []))
        return {normalized.slug, *related}

    def template_slugs(self) -> list[str]:
        return ["fuel", "restaurants", "supermarkets", "pharmacy", "movies", "travel", "home_goods"]
