from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem

# Hard limits — chosen to cover any plausible real-world bank offer while
# capping pathological inputs that would bloat the DB or break the UI.
_MAX_BANK_NAME_LENGTH = 80
_MAX_ITEMS_PER_BANK = 50
_MAX_PERCENT = Decimal("100")
# Categories above this threshold are still saved but flagged; categories
# above _MAX_PERCENT are rejected outright as obviously wrong (a typo like
# "АЗС 500%").
_DECIMAL_ZERO = Decimal("0")


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
        cleaned_name = (bank_name or "").strip()
        if not cleaned_name:
            raise ValidationError("errors.invalid_bank_name")
        if len(cleaned_name) > _MAX_BANK_NAME_LENGTH:
            raise ValidationError(
                "errors.bank_name_too_long",
                {"max_length": _MAX_BANK_NAME_LENGTH},
            )
        if not items:
            raise ValidationError("errors.no_items_to_save")
        if len(items) > _MAX_ITEMS_PER_BANK:
            raise ValidationError(
                "errors.too_many_items",
                {"max_items": _MAX_ITEMS_PER_BANK},
            )
        for item in items:
            if item.percent <= _DECIMAL_ZERO:
                raise ValidationError("errors.zero_percent_not_allowed")
            if item.percent > _MAX_PERCENT:
                raise ValidationError(
                    "errors.percent_out_of_range",
                    {"max_percent": str(_MAX_PERCENT)},
                )
        # Use the cleaned name throughout so the persisted record never
        # carries leading/trailing whitespace that would later complicate
        # case-insensitive lookups.
        bank_name = cleaned_name

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
            await uow.logs.add(
                user_id,
                "bank_added" if created else "bank_updated",
                {"bank_id": bank.id, "bank_name": bank.bank_name},
            )
            await uow.commit()
            # Drop any cached ranking snapshot for this user so the next inline
            # query / /top shows the new items immediately.
            RankingSnapshotUseCase.invalidate(user_id)
            return bank.id
