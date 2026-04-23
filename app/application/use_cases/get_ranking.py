from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases._ranking_shared import fetch_user_ranking_entries
from app.domain.models import BankScore, CategoryLeader
from app.domain.services.ranking import RankingService


class GetRankingUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], ranking: RankingService) -> None:
        self.uow_factory = uow_factory
        self.ranking = ranking

    async def top_by_category(self, user_id: int, language: str) -> list[CategoryLeader]:
        entries = await fetch_user_ranking_entries(self.uow_factory, user_id)
        return self.ranking.top_by_category(entries, language)

    async def top_global(self, user_id: int, language: str) -> list[BankScore]:
        entries = await fetch_user_ranking_entries(self.uow_factory, user_id)
        return self.ranking.top_global(entries, language)
