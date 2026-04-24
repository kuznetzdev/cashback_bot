from __future__ import annotations

from collections.abc import Callable

from app.application.months import current_month_key, normalize_month_key
from app.application.contracts.ports import UnitOfWorkPort
from app.domain.errors import NotFoundError
from app.domain.models import BankAggregate


class GetBankDetailsUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, bank_id: int, target_month: str | None = None) -> BankAggregate:
        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, bank_id)
            if bank is None:
                raise NotFoundError("errors.bank_not_found")
            available_months = await uow.cashback.list_months_for_bank(bank.id)
            selected_month = _resolve_target_month(target_month, available_months)
            items = await uow.cashback.list_for_bank(bank.id, selected_month)
            return BankAggregate(
                bank=bank,
                items=items,
                target_month=selected_month,
                available_months=available_months,
            )


def _resolve_target_month(target_month: str | None, available_months: list[str]) -> str:
    if target_month is not None:
        return normalize_month_key(target_month)
    current_month = current_month_key()
    if current_month in available_months:
        return current_month
    if available_months:
        return available_months[-1]
    return current_month
