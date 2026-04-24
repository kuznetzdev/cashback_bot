from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.services.ranking import RankingEntry


async def fetch_user_ranking_entries(
    uow_factory: Callable[[], UnitOfWorkPort],
    user_id: int,
) -> list[RankingEntry]:
    entries: list[RankingEntry] = []
    async with uow_factory() as uow:
        banks = await uow.banks.list_for_user(user_id)
        for bank in banks:
            items = await uow.cashback.list_for_bank(bank.id)
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
