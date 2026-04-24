from __future__ import annotations

from collections.abc import Callable

from app.application.months import current_month_key
from app.application.contracts.ports import UnitOfWorkPort
from app.domain.models import BankScore, CategoryLeader
from app.domain.services.ranking import RankingEntry, RankingService


class GetRankingUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], ranking: RankingService) -> None:
        self.uow_factory = uow_factory
        self.ranking = ranking

    async def top_by_category(self, user_id: int, language: str) -> list[CategoryLeader]:
        entries = await self._entries_for_user(user_id)
        return self.ranking.top_by_category(entries, language)

    async def top_global(self, user_id: int, language: str) -> list[BankScore]:
        entries = await self._entries_for_user(user_id)
        return self.ranking.top_global(entries, language)

    async def _entries_for_user(self, user_id: int) -> list[RankingEntry]:
        entries: list[RankingEntry] = []
        target_month = current_month_key()
        async with self.uow_factory() as uow:
            banks = await uow.banks.list_for_user(user_id)
            for bank in banks:
                items = await uow.cashback.list_for_bank(bank.id, target_month)
                for item in items:
                    entries.append(
                        RankingEntry(
                            bank_id=bank.id,
                            bank_name=bank.bank_name,
                            category_slug=item.normalized_category,
                            percent=item.percent,
                        )
                    )
        return entries
