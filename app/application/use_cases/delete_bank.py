from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.errors import NotFoundError


class DeleteBankUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, bank_id: int) -> None:
        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, bank_id)
            if bank is None:
                raise NotFoundError("errors.bank_not_found")
            await uow.banks.delete(bank.id)
            await uow.logs.add(user_id, "bank_deleted", {"bank_id": bank.id, "bank_name": bank.bank_name})
            await uow.commit()
