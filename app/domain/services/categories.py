from __future__ import annotations

import hashlib
import re
from collections import OrderedDict

from rapidfuzz import process

from app.domain.models import NormalizedCategory

# Telegram callback_data is capped at 64 bytes. Our callback keys have prefixes
# up to ~20 bytes ("nav:top_category:"), so the slug portion must stay under
# ~40 bytes to keep inline keyboards working. Slugs produced from known
# categories are short ASCII, but user-uploaded OCR can yield arbitrarily long
# Russian phrases — those MUST be hash-suffixed rather than silently truncated,
# otherwise distinct categories would collide into the same bucket.
_MAX_SLUG_BYTES = 40


class CategoryService:
    def __init__(self) -> None:
        self._definitions: dict[str, dict[str, object]] = {
            "fuel": {
                "ru": "АЗС",
                "en": "Fuel",
                "synonyms": [
                    "азс",
                    "заправка",
                    "заправки",
                    "топливо",
                    "бензин",
                    "топливо и азс",
                    "азс и топливо",
                    "fuel",
                    "fuel station",
                    "gas",
                    "gas station",
                    "petrol",
                ],
                "related": [],
            },
            "restaurants": {
                "ru": "Рестораны",
                "en": "Restaurants",
                "synonyms": [
                    "ресторан",
                    "рестораны",
                    "кафе",
                    "кафе и рестораны",
                    "кафе, бары и рестораны",
                    "кафе бары и рестораны",
                    "бары",
                    "рестораны и доставка еды",
                    "ресторан и доставка еды",
                    "food",
                    "dining",
                    "restaurant",
                    "restaurants",
                    "cafe",
                ],
                "related": [],
            },
            "fast_food": {
                "ru": "Фастфуд",
                "en": "Fast food",
                "synonyms": ["фастфуд", "быстрое питание", "fast food", "fastfood", "burger"],
                "related": [],
            },
            "supermarkets": {
                "ru": "Супермаркеты",
                "en": "Supermarkets",
                "synonyms": [
                    "супермаркет",
                    "супермаркеты",
                    "в супермаркетах",
                    "продукты",
                    "supermarket",
                    "supermarkets",
                    "groceries",
                ],
                "related": ["groceries"],
            },
            "groceries": {
                "ru": "Продукты питания",
                "en": "Groceries",
                "synonyms": [
                    "продукты питания",
                    "продуктовый магазин",
                    "grocery",
                    "groceries",
                    "food store",
                ],
                "related": ["supermarkets"],
            },
            "pharmacy": {
                "ru": "Аптеки",
                "en": "Pharmacy",
                "synonyms": [
                    "аптека",
                    "аптеки",
                    "лекарства",
                    "лекарства и товары для здоровья",
                    "товары для здоровья",
                    "pharmacy",
                    "drugstore",
                ],
                "related": [],
            },
            "movies": {
                "ru": "Кино",
                "en": "Movies",
                "synonyms": ["кино", "кинотеатр", "кинотеатры", "cinema", "movie", "movies"],
                "related": [],
            },
            "travel": {
                "ru": "Путешествия",
                "en": "Travel",
                "synonyms": ["путешествия", "поездки", "билеты", "travel", "trip", "tickets"],
                "related": ["hotels"],
            },
            "hotels": {
                "ru": "Отели",
                "en": "Hotels",
                "synonyms": ["отель", "отели", "гостиницы", "hotel", "hotels"],
                "related": [],
            },
            "railway": {
                "ru": "Ж/Д билеты",
                "en": "Railway tickets",
                "synonyms": [
                    "жд",
                    "ж/д",
                    "ж/д билеты",
                    "жд билеты",
                    "железнодорожные билеты",
                    "поезд",
                    "railway",
                    "train",
                    "train tickets",
                ],
                "related": [],
            },
            "transport": {
                "ru": "Транспорт",
                "en": "Transport",
                "synonyms": [
                    "транспорт",
                    "такси",
                    "каршеринг",
                    "такси и каршеринг",
                    "метро",
                    "автобус",
                    "transport",
                    "taxi",
                    "carsharing",
                ],
                "related": [],
            },
            "auto_services": {
                "ru": "Автоуслуги",
                "en": "Auto services",
                "synonyms": [
                    "автоуслуги",
                    "автосервис",
                    "автосервисы",
                    "авто услуги",
                    "мойка",
                    "auto services",
                    "car service",
                    "car wash",
                ],
                "related": [],
            },
            "home_goods": {
                "ru": "Товары для дома",
                "en": "Home goods",
                "synonyms": [
                    "товары для дома",
                    "для дома",
                    "дом и ремонт",
                    "ремонт и дом",
                    "home goods",
                    "home",
                    "household",
                ],
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
            "clothing": {
                "ru": "Одежда и обувь",
                "en": "Clothing",
                "synonyms": [
                    "одежда",
                    "обувь",
                    "одежда и обувь",
                    "shoes",
                    "clothing",
                    "apparel",
                ],
                "related": [],
            },
            "shopping": {
                "ru": "Шопинг",
                "en": "Shopping",
                "synonyms": ["шопинг", "покупки", "shopping", "retail"],
                "related": [],
            },
            "entertainment": {
                "ru": "Развлечения",
                "en": "Entertainment",
                "synonyms": [
                    "развлечения",
                    "хобби",
                    "хобби и развлечения",
                    "развлечения и хобби",
                    "entertainment",
                    "hobby",
                    "hobbies",
                ],
                "related": [],
            },
            "theatre": {
                "ru": "Театры и концерты",
                "en": "Theatre & concerts",
                "synonyms": [
                    "театр",
                    "театры",
                    "концерт",
                    "концерты",
                    "театры и концерты",
                    "theatre",
                    "theater",
                    "concerts",
                ],
                "related": [],
            },
            "books": {
                "ru": "Книги",
                "en": "Books",
                "synonyms": ["книги", "книга", "book", "books", "bookstore"],
                "related": [],
            },
            "sports": {
                "ru": "Спорттовары",
                "en": "Sports",
                "synonyms": [
                    "спорт",
                    "спорттовары",
                    "спорттовары и фитнес",
                    "спортмастер",
                    "sports",
                    "sport",
                    "fitness",
                ],
                "related": [],
            },
            "telecom": {
                "ru": "Связь",
                "en": "Telecom",
                "synonyms": [
                    "связь",
                    "мобильная связь",
                    "оплата связи",
                    "интернет",
                    "telecom",
                    "mobile",
                    "phone bill",
                ],
                "related": [],
            },
            "delivery": {
                "ru": "Доставка",
                "en": "Delivery",
                "synonyms": [
                    "доставка",
                    "доставка еды",
                    "доставка продуктов",
                    "delivery",
                    "food delivery",
                ],
                "related": [],
            },
            "all_purchases": {
                "ru": "На все покупки",
                "en": "All purchases",
                "synonyms": [
                    "на все покупки",
                    "все покупки",
                    "за все",
                    "за всё",
                    "1% за всё",
                    "все",
                    "на всё",
                    "all purchases",
                    "everything",
                    "base cashback",
                ],
                "related": [],
            },
            "beauty": {
                "ru": "Красота",
                "en": "Beauty",
                "synonyms": [
                    "красота",
                    "салоны красоты",
                    "салоны красоты и косметика",
                    "косметика",
                    "бьюти",
                    "парикмахерская",
                    "beauty",
                    "cosmetics",
                    "salon",
                ],
                "related": [],
            },
            "children_goods": {
                "ru": "Детские товары",
                "en": "Kids",
                "synonyms": [
                    "детские товары",
                    "детство",
                    "товары для детей",
                    "для детей",
                    "kids",
                    "children",
                    "baby",
                ],
                "related": [],
            },
            "electronics": {
                "ru": "Электроника",
                "en": "Electronics",
                "synonyms": [
                    "электроника",
                    "техника",
                    "бытовая техника",
                    "гаджеты",
                    "electronics",
                    "gadgets",
                    "consumer electronics",
                ],
                "related": [],
            },
            "marketplaces": {
                "ru": "Маркетплейсы",
                "en": "Marketplaces",
                "synonyms": [
                    "маркетплейс",
                    "маркетплейсы",
                    "онлайн-покупки",
                    "онлайн покупки",
                    "интернет-магазины",
                    "интернет магазины",
                    "маркетплейсы и интернет-магазины",
                    "marketplace",
                    "marketplaces",
                    "online shopping",
                    "e-commerce",
                ],
                "related": [],
            },
        }
        self._term_to_slug: dict[str, str] = {}
        for slug, definition in self._definitions.items():
            terms = [slug, definition["ru"], definition["en"], *definition["synonyms"]]
            for term in terms:
                self._term_to_slug[self._normalize_text(term)] = slug
        # Disambiguation bias: generic product searches → supermarkets slug.
        self._term_to_slug["groceries"] = "supermarkets"
        self._term_to_slug["продукты"] = "supermarkets"
        self._term_to_slug["продукты питания"] = "supermarkets"
        # LRU-evicted cache for normalize() results. Sized to comfortably hold
        # every realistic OCR category phrase users send (bank UIs have ~dozens
        # of distinct category strings per language). Keyed by the raw input so
        # two callers with the same prompt share the hit.
        self._normalize_cache: OrderedDict[str, NormalizedCategory] = OrderedDict()
        self._normalize_cache_maxsize = 2048
        # Diagnostics hit counters — exposed via :meth:`cache_stats` so tests
        # and ops can confirm the cache is actually taking load.
        self._cache_hits = 0
        self._cache_misses = 0

    @staticmethod
    def _normalize_text(value: str) -> str:
        # Strip common qualifier noise that banks append ("в Городе", «в сентябре»,
        # "с МТС Premium") so the same base category matches across providers.
        lowered = re.sub(r"\s+", " ", value.strip().lower())
        for qualifier in (
            " в городе",
            " в москве",
            " с подпиской",
            " при оплате",
            " с мтс premium",
            " со сберпрайм",
            " с тинькофф",
            " для клиентов",
        ):
            if qualifier in lowered:
                lowered = lowered.split(qualifier, 1)[0].strip()
        return lowered

    def _slugify(self, value: str) -> str:
        normalized = self._normalize_text(value)
        cleaned = re.sub(r"[^\w\s-]", "", normalized)
        base = re.sub(r"[\s-]+", "_", cleaned).strip("_") or "other"
        encoded = base.encode("utf-8")
        if len(encoded) <= _MAX_SLUG_BYTES:
            return base
        suffix = hashlib.sha1(encoded, usedforsecurity=False).hexdigest()[:8]
        # Reserve 9 bytes for the "_<hex8>" stable suffix so the total stays
        # under the limit; decode with errors="ignore" in case the byte cut
        # lands mid-UTF-8 sequence.
        head_bytes = encoded[: _MAX_SLUG_BYTES - 9]
        head = head_bytes.decode("utf-8", errors="ignore").rstrip("_")
        return f"{head}_{suffix}" if head else suffix

    def normalize(self, raw: str) -> NormalizedCategory:
        # Cache on the raw input: fast path avoids the expensive rapidfuzz
        # extraction, which runs on every OCR token and can cost milliseconds
        # for long strings. Re-insert on hit to preserve LRU order.
        cached = self._normalize_cache.get(raw)
        if cached is not None:
            self._cache_hits += 1
            self._normalize_cache.move_to_end(raw)
            return cached
        self._cache_misses += 1
        normalized_raw = self._normalize_text(raw)
        slug = self._term_to_slug.get(normalized_raw)
        if slug is None:
            fuzzy = process.extractOne(normalized_raw, self._term_to_slug.keys(), score_cutoff=80)
            if fuzzy:
                slug = self._term_to_slug[fuzzy[0]]
        if slug is None:
            title = raw.strip().title()
            result = NormalizedCategory(slug=self._slugify(raw), display_ru=title, display_en=title)
        else:
            definition = self._definitions[slug]
            result = NormalizedCategory(slug=slug, display_ru=definition["ru"], display_en=definition["en"])
        self._normalize_cache[raw] = result
        if len(self._normalize_cache) > self._normalize_cache_maxsize:
            # Evict the least-recently-used entry — the first in OrderedDict.
            self._normalize_cache.popitem(last=False)
        return result

    def cache_stats(self) -> dict[str, int]:
        """Return cache counters for tests and operational diagnostics."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._normalize_cache),
        }

    def clear_cache(self) -> None:
        """Reset the cache — primarily for test isolation."""
        self._normalize_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

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
        return [
            "fuel",
            "restaurants",
            "supermarkets",
            "pharmacy",
            "movies",
            "travel",
            "home_goods",
            "clothing",
            "entertainment",
            "telecom",
            "transport",
        ]
