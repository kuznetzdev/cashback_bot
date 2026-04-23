from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases._ranking_shared import fetch_user_ranking_entries
from app.domain.models import CategoryLeader
from app.domain.services.categories import CategoryService
from app.domain.services.ranking import RankingService


@dataclass(slots=True)
class RankingSnapshot:
    leaders: list[CategoryLeader]
    query: str
    normalized_slug: str
    display_name: str
    best_match: CategoryLeader | None


class RankingSnapshotUseCase:
    """Fetch the user's ranking entries exactly once and derive both the full
    top-by-category list AND (optionally) the best-match leader for a free-form
    query. Used by stateless entry points like Telegram inline mode where we
    need both answers per request but can't afford two separate DB scans."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        ranking: RankingService,
        categories: CategoryService,
    ) -> None:
        self.uow_factory = uow_factory
        self.ranking = ranking
        self.categories = categories

    async def execute(
        self,
        *,
        user_id: int,
        language: str,
        query: str = "",
    ) -> RankingSnapshot:
        entries = await fetch_user_ranking_entries(self.uow_factory, user_id)
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
