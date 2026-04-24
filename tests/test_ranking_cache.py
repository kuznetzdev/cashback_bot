from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.domain.services.categories import CategoryService
from app.domain.services.ranking import RankingService


class _FakeClock:
    """Small monotonic-style clock so tests can drive TTL deterministically."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def _make_use_case(clock: _FakeClock, ttl: float = 30.0) -> RankingSnapshotUseCase:
    categories = CategoryService()
    ranking = RankingService(categories=categories)
    uow_factory = AsyncMock()
    use_case = RankingSnapshotUseCase(
        uow_factory=uow_factory,
        ranking=ranking,
        categories=categories,
        ttl_seconds=ttl,
        clock=clock,
    )
    return use_case


@pytest.mark.asyncio
async def test_repeated_execute_serves_from_cache_within_ttl() -> None:
    RankingSnapshotUseCase.clear_cache()
    clock = _FakeClock()
    use_case = _make_use_case(clock)
    with patch(
        "app.application.use_cases.ranking_snapshot.fetch_user_ranking_entries",
        AsyncMock(return_value=[]),
    ) as fetch:
        await use_case.execute(user_id=1, language="ru")
        await use_case.execute(user_id=1, language="ru", query="АЗС")
        await use_case.execute(user_id=1, language="ru", query="")
    assert fetch.await_count == 1, (
        "Second + third execute() must serve entries from cache, not the DB"
    )


@pytest.mark.asyncio
async def test_cache_expires_after_ttl() -> None:
    RankingSnapshotUseCase.clear_cache()
    clock = _FakeClock()
    use_case = _make_use_case(clock, ttl=30.0)
    with patch(
        "app.application.use_cases.ranking_snapshot.fetch_user_ranking_entries",
        AsyncMock(return_value=[]),
    ) as fetch:
        await use_case.execute(user_id=7, language="ru")
        clock.tick(29.0)
        await use_case.execute(user_id=7, language="ru")
        assert fetch.await_count == 1
        clock.tick(2.0)  # now past the 30s ttl
        await use_case.execute(user_id=7, language="ru")
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_invalidate_forces_refetch_on_next_execute() -> None:
    RankingSnapshotUseCase.clear_cache()
    clock = _FakeClock()
    use_case = _make_use_case(clock)
    with patch(
        "app.application.use_cases.ranking_snapshot.fetch_user_ranking_entries",
        AsyncMock(return_value=[]),
    ) as fetch:
        await use_case.execute(user_id=9, language="ru")
        RankingSnapshotUseCase.invalidate(9)
        await use_case.execute(user_id=9, language="ru")
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_cache_is_scoped_per_user() -> None:
    RankingSnapshotUseCase.clear_cache()
    clock = _FakeClock()
    use_case = _make_use_case(clock)
    with patch(
        "app.application.use_cases.ranking_snapshot.fetch_user_ranking_entries",
        AsyncMock(return_value=[]),
    ) as fetch:
        await use_case.execute(user_id=1, language="ru")
        await use_case.execute(user_id=2, language="ru")
        await use_case.execute(user_id=1, language="ru")
        await use_case.execute(user_id=2, language="ru")
    assert fetch.await_count == 2
