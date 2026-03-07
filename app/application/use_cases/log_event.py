from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort


class LogEventUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, action: str, payload: dict[str, object] | None = None) -> None:
        async with self.uow_factory() as uow:
            await uow.logs.add(user_id, action, payload)
            await uow.commit()
