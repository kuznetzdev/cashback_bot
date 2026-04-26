"""Self-service data import.

Accepts an :class:`ExportedUser`-shaped dict (or its JSON serialisation)
and replaces the user's banks + cashback items with the import payload.
Designed to round-trip with :class:`ExportUserDataUseCase` — exporting
and importing back must give an equivalent state.

Decisions:

* **Replace, don't merge.** Merging two cashback datasets is ambiguous
  ("which percent wins?"); the user almost always wants what they're
  importing to win. We document this loudly and never silently merge.
* **Skip-and-warn on bad rows** rather than aborting the whole import.
  One unparseable percent shouldn't lose 30 valid offers.
* **Hard size cap** — at most ``_MAX_BANKS`` banks per import and
  ``_MAX_ITEMS_PER_BANK`` items per bank, so a malicious payload can't
  flood the database via a single web upload.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.application.use_cases.save_bank_draft import (
    _MAX_BANK_NAME_LENGTH,
    _MAX_ITEMS_PER_BANK,
)
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem

_MAX_BANKS = 100  # plausible ceiling; far above any real user's portfolio
_DECIMAL_ZERO = Decimal("0")
_DECIMAL_HUNDRED = Decimal("100")


@dataclass(slots=True)
class ImportResult:
    banks_imported: int = 0
    items_imported: int = 0
    skipped_banks: list[str] = field(default_factory=list)
    skipped_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ImportUserDataUseCase:
    """Replace ``user_id``'s banks + items with the contents of ``payload``.

    The import always runs through the regular UoW — same transactional
    guarantees as a normal save. If the payload is empty or malformed at
    the top level, raises :class:`ValidationError`; per-bank and per-item
    issues are collected as warnings without aborting the rest of the
    import.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(
        self,
        *,
        user_id: int,
        payload: dict[str, Any] | str,
    ) -> ImportResult:
        data = self._parse_payload(payload)
        banks_payload = self._extract_banks(data)

        result = ImportResult()

        async with self.uow_factory() as uow:
            # Preserve the user's display name / language; only banks +
            # items are replaced. We deliberately don't trust the
            # ``user`` block from the payload — it could change identity
            # fields cross-account if accepted blindly.
            existing_banks = await uow.banks.list_for_user(user_id)
            for existing in existing_banks:
                await uow.banks.delete(existing.id)

            for bank_index, bank_obj in enumerate(banks_payload):
                if not isinstance(bank_obj, dict):
                    result.skipped_banks.append(f"#{bank_index}: not an object")
                    continue
                bank_name = self._sanitise_bank_name(bank_obj.get("bank_name"))
                if bank_name is None:
                    result.skipped_banks.append(f"#{bank_index}: invalid bank_name")
                    continue
                items_obj = bank_obj.get("items")
                if not isinstance(items_obj, list):
                    result.skipped_banks.append(f"{bank_name}: items missing")
                    continue
                accepted_items: list[CashbackDraftItem] = []
                for item_index, raw_item in enumerate(items_obj):
                    parsed = self._parse_item(raw_item)
                    if parsed is None:
                        result.skipped_items.append(f"{bank_name}[#{item_index}]")
                        continue
                    accepted_items.append(parsed)
                    if len(accepted_items) >= _MAX_ITEMS_PER_BANK:
                        result.warnings.append(f"{bank_name}: truncated to {_MAX_ITEMS_PER_BANK} items")
                        break
                if not accepted_items:
                    result.skipped_banks.append(f"{bank_name}: no valid items")
                    continue
                bank = await uow.banks.create(user_id, bank_name)
                await uow.cashback.replace_for_bank(bank.id, accepted_items)
                result.banks_imported += 1
                result.items_imported += len(accepted_items)

            await uow.logs.add(
                user_id,
                "data_imported",
                {
                    "banks": result.banks_imported,
                    "items": result.items_imported,
                    "skipped_banks": len(result.skipped_banks),
                    "skipped_items": len(result.skipped_items),
                },
            )
            await uow.commit()

        # Inval cache so /best & inline see the new data immediately.
        RankingSnapshotUseCase.invalidate(user_id)
        return result

    @staticmethod
    def _parse_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as error:
                raise ValidationError("errors.import_invalid_json") from error
        elif isinstance(payload, dict):
            data = payload
        else:
            raise ValidationError("errors.import_invalid_payload")
        if not isinstance(data, dict):
            raise ValidationError("errors.import_invalid_payload")
        return data

    @staticmethod
    def _extract_banks(data: dict[str, Any]) -> list[Any]:
        banks_obj = data.get("banks")
        if not isinstance(banks_obj, list):
            raise ValidationError("errors.import_invalid_payload")
        if len(banks_obj) > _MAX_BANKS:
            raise ValidationError(
                "errors.import_too_many_banks",
                {"max_banks": _MAX_BANKS},
            )
        return banks_obj

    @staticmethod
    def _sanitise_bank_name(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned or len(cleaned) > _MAX_BANK_NAME_LENGTH:
            return None
        return cleaned

    @staticmethod
    def _parse_item(raw: object) -> CashbackDraftItem | None:
        if not isinstance(raw, dict):
            return None
        raw_category = raw.get("raw_category")
        normalized_category = raw.get("normalized_category")
        if not isinstance(raw_category, str) or not raw_category.strip():
            return None
        if not isinstance(normalized_category, str) or not normalized_category.strip():
            return None
        percent = _coerce_decimal(raw.get("percent"))
        if percent is None or percent <= _DECIMAL_ZERO or percent > _DECIMAL_HUNDRED:
            return None
        source_type = raw.get("source_type")
        if not isinstance(source_type, str) or not source_type.strip():
            source_type = "manual"
        monthly_limit = _coerce_decimal(raw.get("monthly_limit"))
        if monthly_limit is not None and monthly_limit <= _DECIMAL_ZERO:
            monthly_limit = None
        return CashbackDraftItem(
            raw_category=raw_category.strip(),
            normalized_category=normalized_category.strip(),
            percent=percent,
            source_type=source_type.strip(),
            monthly_limit=monthly_limit,
        )


def _coerce_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        try:
            return Decimal(value.strip().replace(",", "."))
        except (InvalidOperation, AttributeError):
            return None
    return None
