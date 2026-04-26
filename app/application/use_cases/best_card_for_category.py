from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases._ranking_shared import fetch_user_ranking_entries
from app.domain.models import CategoryLeader
from app.domain.services.categories import CategoryService
from app.domain.services.ranking import RankingService


@dataclass(slots=True)
class BestCardResult:
    query: str
    normalized_slug: str
    display_name: str
    leader: CategoryLeader | None


class BestCardForCategoryUseCase:
    """Central decision-support entry point: 'which of my cards pays the most
    cashback for X right now?'

    Used by the Telegram inline query handler, the /best slash command, the
    free-form "лучший кэшбэк на X" intent parser, and (optionally) navigation.
    Consolidating the flow here ensures the same fuzzy-related-slug behaviour
    (`supermarkets` ↔ `groceries`) is applied everywhere instead of being
    duplicated across entry points.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        ranking: RankingService,
        categories: CategoryService,
    ) -> None:
        self.uow_factory = uow_factory
        self.ranking = ranking
        self.categories = categories

    async def execute(self, *, user_id: int, query: str, language: str) -> BestCardResult:
        cleaned = (query or "").strip()
        normalized = self.categories.normalize(cleaned) if cleaned else None
        slug = normalized.slug if normalized else ""
        display_name = self.categories.display_name(slug, language) if slug else cleaned or ""
        if not slug:
            return BestCardResult(
                query=cleaned,
                normalized_slug="",
                display_name=display_name,
                leader=None,
            )
        entries = await fetch_user_ranking_entries(self.uow_factory, user_id)
        leader = self.ranking.best_for_slug(entries, slug, language) if entries else None
        if leader is not None:
            display_name = leader.category_name
        return BestCardResult(
            query=cleaned,
            normalized_slug=slug,
            display_name=display_name,
            leader=leader,
        )
