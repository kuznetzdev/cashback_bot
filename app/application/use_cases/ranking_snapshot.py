from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases._ranking_shared import fetch_user_ranking_entries
from app.domain.models import CategoryLeader
from app.domain.services.categories import CategoryService
from app.domain.services.ranking import RankingEntry, RankingService


@dataclass(slots=True)
class RankingSnapshot:
    leaders: list[CategoryLeader]
    query: str
    normalized_slug: str
    display_name: str
    best_match: CategoryLeader | None


# TTL in seconds for per-user entry caches. Inline mode can hit this many times
# a minute during autocomplete; 30s hides transient replication lag while
# keeping deletions/updates visible on the next refresh cycle.
_RANKING_CACHE_TTL_SECONDS = 30.0
_RANKING_CACHE_SWEEP_EVERY = 256


class RankingSnapshotUseCase:
    """Fetch the user's ranking entries exactly once and derive both the full
    top-by-category list AND (optionally) the best-match leader for a free-form
    query. Used by stateless entry points like Telegram inline mode where we
    need both answers per request but can't afford two separate DB scans.

    Entries are cached per ``user_id`` for :data:`_RANKING_CACHE_TTL_SECONDS`
    so rapid autocomplete requests don't hammer the DB. Mutating use-cases
    (save/delete bank) must call :meth:`invalidate` so the next read sees the
    change immediately.
    """

    # Process-wide cache: we can't put it on ``self`` because one instance of
    # the use case is re-used across all users, and we don't want one caller
    # to read another's cache. The user_id keying keeps that safe.
    _entries_cache: dict[int, tuple[list[RankingEntry], float]] = {}
    _calls_since_sweep: int = 0

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        ranking: RankingService,
        categories: CategoryService,
        *,
        ttl_seconds: float = _RANKING_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.uow_factory = uow_factory
        self.ranking = ranking
        self.categories = categories
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock

    async def execute(
        self,
        *,
        user_id: int,
        language: str,
        query: str = "",
    ) -> RankingSnapshot:
        entries = self._read_cached(user_id)
        if entries is None:
            entries = await fetch_user_ranking_entries(self.uow_factory, user_id)
            self._store_cached(user_id, entries)
        leaders = self.ranking.top_by_category(entries, language) if entries else []

        cleaned = (query or "").strip()
        if not cleaned:
            return RankingSnapshot(
                leaders=leaders,
                query="",
                normalized_slug="",
                display_name="",
                best_match=None,
            )

        normalized = self.categories.normalize(cleaned)
        slug = normalized.slug
        display_name = self.categories.display_name(slug, language)
        best_match = self.ranking.best_for_slug(entries, slug, language) if entries else None
        if best_match is not None:
            display_name = best_match.category_name
        return RankingSnapshot(
            leaders=leaders,
            query=cleaned,
            normalized_slug=slug,
            display_name=display_name,
            best_match=best_match,
        )

    # ---- cache helpers ----------------------------------------------------

    @classmethod
    def invalidate(cls, user_id: int) -> None:
        """Drop the cached entries for ``user_id``. Call from use cases that
        write to a user's banks/items so subsequent reads see fresh data."""
        cls._entries_cache.pop(user_id, None)

    @classmethod
    def clear_cache(cls) -> None:
        cls._entries_cache.clear()
        cls._calls_since_sweep = 0

    def _read_cached(self, user_id: int) -> list[RankingEntry] | None:
        cached = self._entries_cache.get(user_id)
        if cached is None:
            return None
        entries, expires_at = cached
        if self._clock() >= expires_at:
            self._entries_cache.pop(user_id, None)
            return None
        return entries

    def _store_cached(self, user_id: int, entries: list[RankingEntry]) -> None:
        self._entries_cache[user_id] = (entries, self._clock() + self._ttl_seconds)
        self._maybe_sweep()

    def _maybe_sweep(self) -> None:
        # Periodically drop expired entries so unused per-user caches don't
        # accumulate forever after the user stops querying.
        type(self)._calls_since_sweep += 1
        if type(self)._calls_since_sweep < _RANKING_CACHE_SWEEP_EVERY:
            return
        type(self)._calls_since_sweep = 0
        now = self._clock()
        stale = [uid for uid, (_, expires_at) in self._entries_cache.items() if expires_at <= now]
        for uid in stale:
            self._entries_cache.pop(uid, None)
