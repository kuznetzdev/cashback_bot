from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.domain.errors import NotFoundError
from app.domain.services.categories import CategoryService


class DeleteCategoryUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], categories: CategoryService) -> None:
        self.uow_factory = uow_factory
        self.categories = categories

    async def execute(self, *, user_id: int, query: str) -> tuple[int, int]:
        total_deleted = 0
        affected_banks = 0
        target_slugs = self.categories.expand_query_slugs(query)

        async with self.uow_factory() as uow:
            banks = await uow.banks.list_for_user(user_id)
            for bank in banks:
                items = await uow.cashback.list_for_bank(bank.id)
                remaining = [item for item in items if item.normalized_category not in target_slugs]
                deleted = len(items) - len(remaining)
                if deleted <= 0:
                    continue
                await uow.cashback.replace_for_bank(bank.id, remaining)
                total_deleted += deleted
                affected_banks += 1
            if total_deleted == 0:
                raise NotFoundError("errors.category_not_found")
            await uow.logs.add(
                user_id,
                "category_deleted",
                {"query": query, "deleted_items": total_deleted, "affected_banks": affected_banks},
            )
            await uow.commit()
        RankingSnapshotUseCase.invalidate(user_id)
        return total_deleted, affected_banks
