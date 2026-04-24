from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.services.ranking import RankingEntry


async def fetch_user_ranking_entries(
    uow_factory: Callable[[], UnitOfWorkPort],
    user_id: int,
) -> list[RankingEntry]:
    """Load every (bank, category, percent) row a user owns.

    Uses the bulk ``list_ranking_entries_for_user`` port when the adapter
    implements it (postgres + in-memory tests both do). Falls back to the
    legacy per-bank scan for older adapters that don't expose the bulk
    method yet — keeping compatibility without sacrificing the N+1 fix in
    production.
    """
    async with uow_factory() as uow:
        bulk = getattr(uow.cashback, "list_ranking_entries_for_user", None)
        if callable(bulk):
            return await bulk(user_id)
        # Legacy adapters: keep the old shape working.
        entries: list[RankingEntry] = []
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
