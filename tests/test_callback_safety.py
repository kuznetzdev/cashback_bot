"""Callback-data safety: Telegram rejects buttons with ``callback_data`` over
64 bytes silently (the button becomes inert). These tests pin the defenses
on both layers — the slug producer (``CategoryService._slugify``) and the
encoder (``encode_action``) — so regressions surface as test failures.
"""

from __future__ import annotations

from app.adapters.telegram.callbacks import _CALLBACK_DATA_MAX_BYTES, encode_action
from app.application.models import Action
from app.domain.services.categories import CategoryService


def test_slug_for_unknown_short_category_stays_readable() -> None:
    service = CategoryService()
    slug = service.normalize("Tasty Coffee").slug
    assert slug == "tasty_coffee"
    assert len(slug.encode("utf-8")) <= 40


def test_slug_for_extremely_long_raw_category_gets_hash_suffixed() -> None:
    service = CategoryService()
    raw = "Очень длинная партнёрская категория банка с ограничениями по мерчанту и уровню лояльности"

    slug = service.normalize(raw).slug

    assert len(slug.encode("utf-8")) <= 40, "Long slugs MUST be truncated to fit Telegram callback limits"


def test_long_raw_categories_produce_distinct_slugs() -> None:
    # Two different raw strings must not collide into the same truncated slug —
    # the hash suffix disambiguates them.
    service = CategoryService()
    raw_a = "Очень длинная партнёрская категория банка вариант один"
    raw_b = "Очень длинная партнёрская категория банка вариант два"

    slug_a = service.normalize(raw_a).slug
    slug_b = service.normalize(raw_b).slug

    assert slug_a != slug_b


def test_encoded_callback_for_long_slug_fits_telegram_limit() -> None:
    long_slug = "x" * 80
    action = Action(
        command="open_top_category",
        label_key="buttons.open",
        payload={"slug": long_slug},
    )
    encoded = encode_action(action)
    assert len(encoded.encode("utf-8")) <= _CALLBACK_DATA_MAX_BYTES


def test_encoded_callback_for_normal_slug_is_unmodified() -> None:
    action = Action(
        command="open_top_category",
        label_key="buttons.open",
        payload={"slug": "restaurants"},
    )
    encoded = encode_action(action)
    assert encoded == "nav:top_category:restaurants"


def test_all_known_category_slugs_fit_in_callback_data() -> None:
    # Every shipped category must produce a callback_data that fits Telegram's
    # limit without needing the hash fallback — the fallback is a safety net,
    # not an everyday path.
    service = CategoryService()
    for slug in service._definitions:
        action = Action(
            command="open_top_category",
            label_key=slug,
            payload={"slug": slug},
        )
        encoded = encode_action(action)
        assert len(encoded.encode("utf-8")) <= _CALLBACK_DATA_MAX_BYTES, (
            f"Shipped category slug {slug!r} produces oversized callback_data {encoded!r}"
        )
