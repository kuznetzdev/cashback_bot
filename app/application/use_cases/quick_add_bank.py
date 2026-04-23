from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem
from app.domain.services.parsing import ParserService


@dataclass(slots=True)
class QuickAddResult:
    bank_id: int
    bank_name: str
    items: list[CashbackDraftItem]


# Split cashback lines on commas, newlines, or semicolons so users can type in
# whatever shape they like: ``Tinkoff: АЗС 5%, Рестораны 3%`` or
# ``Tinkoff: АЗС 5%; Рестораны 3%`` or even multi-line.
_ITEM_SEPARATOR = re.compile(r"[,\n;]+")


class QuickAddBankUseCase:
    """Parse a single-line "<bank>: <cat1> <p1>%, <cat2> <p2>%..." payload and
    persist it as a saved bank in one shot. Used by the /quickadd Telegram
    command and by the web 'paste and save' shortcut."""

    def __init__(
        self,
        parser: ParserService,
        save_bank_draft_use_case: SaveBankDraftUseCase,
    ) -> None:
        self.parser = parser
        self.save_bank_draft_use_case = save_bank_draft_use_case

    async def execute(self, *, user_id: int, payload: str) -> QuickAddResult:
        bank_name, items_text = self._split_bank_and_items(payload)
        if not bank_name:
            raise ValidationError("errors.invalid_bank_name")
        if not items_text:
            raise ValidationError("errors.invalid_manual_input")

        # ParserService parses one line at a time; normalise commas/semicolons to newlines.
        normalized = _ITEM_SEPARATOR.sub("\n", items_text)
        items = self.parser.parse_manual_lines(normalized)
        if not items:
            raise ValidationError("errors.invalid_manual_input")

        bank_id = await self.save_bank_draft_use_case.execute(
            user_id=user_id,
            bank_id=None,
            bank_name=bank_name,
            items=items,
        )
        return QuickAddResult(bank_id=bank_id, bank_name=bank_name, items=items)

    @staticmethod
    def _split_bank_and_items(payload: str) -> tuple[str, str]:
        text = (payload or "").strip()
        if not text:
            return "", ""
        # Accept both a colon and a dash as the bank/items separator.
        for separator in (":", "—", "-"):
            if separator in text:
                head, _, tail = text.partition(separator)
                head = head.strip()
                tail = tail.strip()
                if head and tail:
                    return head, tail
        return "", ""
