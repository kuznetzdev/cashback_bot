from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.services.categories import CategoryService


def test_normalize_caches_repeated_lookups() -> None:
    service = CategoryService()
    service.clear_cache()

    # First call populates the cache; fuzzy matcher may or may not be invoked
    # depending on whether the term hits the primary dict. We spy after the
    # first call so the miss is already captured.
    first = service.normalize("АЗС")
    second = service.normalize("АЗС")
    assert first == second
    stats = service.cache_stats()
    assert stats["hits"] >= 1, stats
    assert stats["misses"] == 1, stats


def test_normalize_fuzzy_path_is_only_called_once_per_unique_input() -> None:
    service = CategoryService()
    service.clear_cache()
    value = "какая-то совсем_новая_строка_для_кеша"

    with patch(
        "app.domain.services.categories.process.extractOne",
        wraps=__import__("rapidfuzz").process.extractOne,
    ) as spy:
        service.normalize(value)
        service.normalize(value)
        service.normalize(value)
    # The expensive fuzzy lookup only fires on the first (cache miss) call.
    assert spy.call_count == 1, spy.call_args_list


def test_cache_evicts_oldest_on_overflow() -> None:
    service = CategoryService()
    service.clear_cache()
    service._normalize_cache_maxsize = 3  # type: ignore[attr-defined]
    for i in range(5):
        service.normalize(f"unique-term-{i}")
    assert service.cache_stats()["size"] == 3
    # The first two entries should have been evicted.
    assert "unique-term-0" not in service._normalize_cache  # type: ignore[attr-defined]
    assert "unique-term-4" in service._normalize_cache  # type: ignore[attr-defined]


def test_cache_preserves_lru_order_on_hit() -> None:
    service = CategoryService()
    service.clear_cache()
    service._normalize_cache_maxsize = 3  # type: ignore[attr-defined]
    service.normalize("a-cashback-category-1")
    service.normalize("a-cashback-category-2")
    service.normalize("a-cashback-category-3")
    # Touch the oldest so it moves to MRU.
    service.normalize("a-cashback-category-1")
    # Add one more; now category-2 (the second-oldest after promotion) evicts.
    service.normalize("a-cashback-category-4")
    remaining = service._normalize_cache.keys()  # type: ignore[attr-defined]
    assert "a-cashback-category-1" in remaining
    assert "a-cashback-category-4" in remaining
    assert "a-cashback-category-2" not in remaining
