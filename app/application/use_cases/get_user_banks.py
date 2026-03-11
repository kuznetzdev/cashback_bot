from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.models import Bank


class GetUserBanksUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int) -> list[Bank]:
        async with self.uow_factory() as uow:
            return await uow.banks.list_for_user(user_id)
