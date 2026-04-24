from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem


class SaveBankDraftUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(
        self,
        *,
        user_id: int,
        bank_id: int | None,
        bank_name: str,
        items: list[CashbackDraftItem],
    ) -> int:
        if not bank_name.strip():
            raise ValidationError("errors.invalid_bank_name")
        if not items:
            raise ValidationError("errors.no_items_to_save")
        if any(item.percent <= 0 for item in items):
            raise ValidationError("errors.zero_percent_not_allowed")

        async with self.uow_factory() as uow:
            bank = await uow.banks.get_for_user(user_id, bank_id) if bank_id else None
            created = False
            if bank is None:
                bank = await uow.banks.get_by_name(user_id, bank_name)
            if bank is None:
                bank = await uow.banks.create(user_id, bank_name)
                created = True
            else:
                await uow.banks.update_name(bank.id, bank_name)
            await uow.cashback.replace_for_bank(bank.id, items)
            await uow.logs.add(user_id, "bank_added" if created else "bank_updated", {"bank_id": bank.id, "bank_name": bank.bank_name})
            await uow.commit()
            # Drop any cached ranking snapshot for this user so the next inline
            # query / /top shows the new items immediately.
            RankingSnapshotUseCase.invalidate(user_id)
            return bank.id
