from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.models import UserLogEntry


class GetHistoryUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], limit: int = 20) -> None:
        self.uow_factory = uow_factory
        self.limit = limit

    async def execute(self, *, user_id: int) -> list[UserLogEntry]:
        async with self.uow_factory() as uow:
            return await uow.logs.list_recent(user_id, self.limit)
