from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.telegram.inline import InlineDependencies, handle_inline_query
from app.application.use_cases.ranking_snapshot import RankingSnapshot
from app.domain.models import CategoryLeader, UserAccount
from app.i18n.localizer import Localizer

LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "locales"


def _localizer() -> Localizer:
    return Localizer(locales_dir=LOCALES_DIR, default_language="ru")


def _fake_query(text: str, *, user_id: int | None = 42) -> SimpleNamespace:
    from_user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(query=text, from_user=from_user, answer=AsyncMock())


def _leader(slug: str, name: str, percent: str, banks: list[str]) -> CategoryLeader:
    return CategoryLeader(
        category_slug=slug,
        category_name=name,
        best_percent=Decimal(percent),
        bank_names=banks,
    )


def _make_facade(*, find_user: UserAccount | None, snapshot: RankingSnapshot) -> SimpleNamespace:
    return SimpleNamespace(
        find_user_by_external_identity=AsyncMock(return_value=find_user),
        ranking_snapshot=AsyncMock(return_value=snapshot),
    )


@pytest.fixture
def deps() -> InlineDependencies:
    return InlineDependencies(
        facade=SimpleNamespace(),
        localizer=_localizer(),
        default_language="ru",
        bot_username="cashback_analyzer_bot",
    )


def _empty_snapshot() -> RankingSnapshot:
    return RankingSnapshot(leaders=[], query="", normalized_slug="", display_name="", best_match=None)


@pytest.mark.asyncio
async def test_inline_onboards_unregistered_user(deps):
    deps.facade = _make_facade(find_user=None, snapshot=_empty_snapshot())
    query = _fake_query("АЗС")

    await handle_inline_query(query, deps)

    call_kwargs = query.answer.await_args.kwargs
    assert call_kwargs["is_personal"] is True
    results = call_kwargs["results"]
    assert len(results) == 1
    assert results[0].id == "onboarding"
    assert "Откройте диалог" in results[0].input_message_content.message_text
    assert call_kwargs["switch_pm_text"]


@pytest.mark.asyncio
async def test_inline_prompts_empty_banks(deps):
    user = UserAccount(id=1, display_name="U", language="ru", notifications_enabled=True)
    deps.facade = _make_facade(find_user=user, snapshot=_empty_snapshot())
    query = _fake_query("АЗС")

    await handle_inline_query(query, deps)

    results = query.answer.await_args.kwargs["results"]
    assert len(results) == 1
    assert results[0].id == "empty_banks"


@pytest.mark.asyncio
async def test_inline_shows_top_categories_for_blank_query(deps):
    user = UserAccount(id=1, display_name="U", language="ru", notifications_enabled=True)
    leaders = [
        _leader("fuel", "АЗС", "5", ["Tinkoff"]),
        _leader("restaurants", "Рестораны", "7", ["Alfa"]),
    ]
    snapshot = RankingSnapshot(
        leaders=leaders, query="", normalized_slug="", display_name="", best_match=None
    )
    deps.facade = _make_facade(find_user=user, snapshot=snapshot)
    query = _fake_query("")

    await handle_inline_query(query, deps)

    # Snapshot-based path: exactly one DB-facing facade call per request.
    assert deps.facade.ranking_snapshot.await_count == 1
    results = query.answer.await_args.kwargs["results"]
    titles = [r.title for r in results]
    assert any("АЗС" in t for t in titles)
    assert any("Рестораны" in t for t in titles)


@pytest.mark.asyncio
async def test_inline_returns_match_plus_top_fallback(deps):
    user = UserAccount(id=1, display_name="U", language="ru", notifications_enabled=True)
    leaders = [
        _leader("fuel", "АЗС", "5", ["Tinkoff"]),
        _leader("restaurants", "Рестораны", "7", ["Alfa"]),
    ]
    match = _leader("fuel", "АЗС", "5", ["Tinkoff"])
    snapshot = RankingSnapshot(
        leaders=leaders,
        query="бензин",
        normalized_slug="fuel",
        display_name="АЗС",
        best_match=match,
    )
    deps.facade = _make_facade(find_user=user, snapshot=snapshot)
    query = _fake_query("бензин")

    await handle_inline_query(query, deps)

    results = query.answer.await_args.kwargs["results"]
    assert results[0].title.startswith("АЗС")
    assert "Tinkoff" in results[0].input_message_content.message_text
    assert len(results) >= 2  # match + at least one fallback


@pytest.mark.asyncio
async def test_inline_returns_no_match_result_with_fallback(deps):
    user = UserAccount(id=1, display_name="U", language="ru", notifications_enabled=True)
    leaders = [_leader("fuel", "АЗС", "5", ["Tinkoff"])]
    snapshot = RankingSnapshot(
        leaders=leaders,
        query="кино",
        normalized_slug="movies",
        display_name="Кино",
        best_match=None,
    )
    deps.facade = _make_facade(find_user=user, snapshot=snapshot)
    query = _fake_query("кино")

    await handle_inline_query(query, deps)

    results = query.answer.await_args.kwargs["results"]
    assert "кино" in results[0].title
    assert len(results) == 2


@pytest.mark.asyncio
async def test_inline_empty_results_when_from_user_missing(deps):
    query = _fake_query("АЗС", user_id=None)

    await handle_inline_query(query, deps)

    assert query.answer.await_args.kwargs["results"] == []


@pytest.mark.asyncio
async def test_inline_result_ids_stay_within_64_chars(deps):
    user = UserAccount(id=1, display_name="U", language="ru", notifications_enabled=True)
    leaders = [_leader("fuel", "АЗС", "5", ["Tinkoff"])]
    snapshot = RankingSnapshot(
        leaders=leaders, query="", normalized_slug="", display_name="", best_match=None
    )
    deps.facade = _make_facade(find_user=user, snapshot=snapshot)
    query = _fake_query("")

    await handle_inline_query(query, deps)

    for result in query.answer.await_args.kwargs["results"]:
        assert 0 < len(result.id) <= 64
