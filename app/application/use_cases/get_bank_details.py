from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.errors import NotFoundError
from app.domain.models import BankAggregate


class GetBankDetailsUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, bank_id: int) -> BankAggregate:
        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, bank_id)
            if bank is None:
                raise NotFoundError("errors.bank_not_found")
            items = await uow.cashback.list_for_bank(bank.id)
            return BankAggregate(bank=bank, items=items)
