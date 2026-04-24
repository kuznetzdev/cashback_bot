from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from rapidfuzz import process

from app.application.contracts.ports import UnitOfWorkPort
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService


@dataclass(slots=True)
class QuickAddResult:
    """Single-bank result — kept for backward compatibility.

    Callers that still expect ``{bank_id, bank_name, items}`` (Telegram
    ``/quickadd``'s happy path) keep working. New callers that need the
    multi-bank batch behaviour should read :attr:`batch` for the full picture.
    """

    bank_id: int
    bank_name: str
    items: list[CashbackDraftItem]
    batch: "QuickAddBatchResult | None" = None


@dataclass(slots=True)
class QuickAddBatchResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    banks: list[QuickAddResult] = field(default_factory=list)


# Separator semantics:
#   * newline/semicolon always splits items;
#   * a comma only splits if it isn't between two digits (so "2,5" stays a
#     decimal number but "АЗС 5%, Рестораны 3%" splits correctly).
_ITEM_SEPARATOR = re.compile(r"[\n;]+|(?<!\d),(?!\d)")


class QuickAddBankUseCase:
    """Parse a ``<bank>: <cat> <p>%, ...`` payload and persist the resulting
    bank(s). Supports two shapes:

    * **Single bank** (legacy): one line with a colon separator.
    * **Multi-bank batch**: multiple banks separated by a blank line or by a
      standalone bank-name line. Each block is parsed independently and
      committed; partial failures return warnings rather than aborting the
      whole batch.

    Validation feedback:
    * Unknown (or OCR-garbled) categories surface as warnings with a
      rapidfuzz suggestion when the Levenshtein distance is close enough.
    * Percentages above 30% surface a warning so the user double-checks
      before saving a typo like "АЗС 50%" (a common mistake with decimals).
    * Banks that already exist for the user are reported in ``updated``
      instead of ``added``.
    """

    _WARN_HIGH_PERCENT = Decimal("30")
    _FUZZY_SUGGESTION_CUTOFF = 60

    def __init__(
        self,
        parser: ParserService,
        save_bank_draft_use_case: SaveBankDraftUseCase,
        categories: CategoryService | None = None,
        uow_factory: Callable[[], UnitOfWorkPort] | None = None,
    ) -> None:
        self.parser = parser
        self.save_bank_draft_use_case = save_bank_draft_use_case
        # Used for fuzzy "did-you-mean" suggestions on unknown categories.
        # We deliberately accept ``None`` so existing two-argument
        # construction in tests keeps working.
        self.categories = categories
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, payload: str) -> QuickAddResult:
        blocks = _split_bank_blocks(payload)
        if not blocks:
            raise ValidationError("errors.invalid_bank_name")

        batch = QuickAddBatchResult()
        first_result: QuickAddResult | None = None

        for block in blocks:
            bank_name, items_text = self._split_bank_and_items(block)
            if not bank_name:
                # For a single-block payload, keep the original error contract.
                if len(blocks) == 1:
                    raise ValidationError("errors.invalid_bank_name")
                batch.warnings.append(f"⚠️ Не распознан банк в блоке: {block[:40]!r}")
                continue
            if not items_text:
                if len(blocks) == 1:
                    raise ValidationError("errors.invalid_manual_input")
                batch.warnings.append(f"⚠️ {bank_name}: не найдено ни одной категории")
                continue

            normalized = _ITEM_SEPARATOR.sub("\n", items_text)
            parsed_items, block_warnings = self._parse_with_feedback(normalized)
            batch.warnings.extend([f"{bank_name}: {warn}" for warn in block_warnings])
            if not parsed_items:
                if len(blocks) == 1:
                    raise ValidationError("errors.invalid_manual_input")
                batch.warnings.append(f"⚠️ {bank_name}: ни одна категория не распознана")
                continue

            existed = await self._bank_exists(user_id=user_id, bank_name=bank_name)
            bank_id = await self.save_bank_draft_use_case.execute(
                user_id=user_id,
                bank_id=None,
                bank_name=bank_name,
                items=parsed_items,
            )
            result = QuickAddResult(bank_id=bank_id, bank_name=bank_name, items=parsed_items)
            batch.banks.append(result)
            (batch.updated if existed else batch.added).append(bank_name)
            if first_result is None:
                first_result = result

        if first_result is None:
            raise ValidationError("errors.invalid_manual_input")

        first_result.batch = batch
        return first_result

    def _parse_with_feedback(
        self, normalized_text: str
    ) -> tuple[list[CashbackDraftItem], list[str]]:
        """Parse manual lines and collect warnings for unknown categories and
        suspicious percentages. Items that *can* be parsed are still returned
        — we prefer degrading gracefully to bailing on a whole block."""
        items = self.parser.parse_manual_lines(normalized_text)
        warnings: list[str] = []

        known_slugs: set[str] = set()
        if self.categories is not None:
            known_slugs = {slug for slug in self.categories._definitions.keys()}  # type: ignore[attr-defined]

        for item in items:
            if item.percent > self._WARN_HIGH_PERCENT:
                warnings.append(
                    f"⚠️ Необычно высокий кешбэк {item.raw_category} {item.percent}% — проверь"
                )
            # The normalizer returns the raw slug when it couldn't find a match
            # (title-cased bytes hashed into a slug). Flag those so the user
            # can confirm/correct the category name.
            if known_slugs and item.normalized_category not in known_slugs:
                suggestion = self._suggest_category(item.raw_category)
                if suggestion is not None:
                    warnings.append(
                        f"⚠️ Не распознано: '{item.raw_category}' — "
                        f"возможно имели в виду '{suggestion}'?"
                    )
                else:
                    warnings.append(
                        f"⚠️ Не распознано: '{item.raw_category}'. Будет сохранено как есть."
                    )

        return items, warnings

    def _suggest_category(self, raw: str) -> str | None:
        if self.categories is None:
            return None
        # Compare against the keys of ``_term_to_slug`` so we match either the
        # canonical slug or any synonym the user likely recalled.
        candidates = list(self.categories._term_to_slug.keys())  # type: ignore[attr-defined]
        match = process.extractOne(
            (raw or "").strip().lower(),
            candidates,
            score_cutoff=self._FUZZY_SUGGESTION_CUTOFF,
        )
        if match is None:
            return None
        slug = self.categories._term_to_slug[match[0]]  # type: ignore[attr-defined]
        return slug

    async def _bank_exists(self, *, user_id: int, bank_name: str) -> bool:
        if self.uow_factory is None:
            return False
        try:
            async with self.uow_factory() as uow:
                bank = await uow.banks.get_by_name(user_id, bank_name)
                return bank is not None
        except Exception:
            return False

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


def _split_bank_blocks(payload: str) -> list[str]:
    """Split a multi-bank quickadd payload into per-bank blocks.

    Two supported shapes:

    1. Paragraph form (blank line between blocks)::

           Tinkoff:
           АЗС 5%, Рестораны 3%

           Sber:
           Супермаркеты 10%, Аптеки 7%

    2. Inline form (single block, single line). In that case we return a
       list with one element so the single-bank path is preserved.

    Blocks are trimmed; empty blocks are dropped.
    """
    text = (payload or "").strip()
    if not text:
        return []
    # Normalise Windows line endings then split on runs of blank lines.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized)]
    return [block for block in blocks if block]
