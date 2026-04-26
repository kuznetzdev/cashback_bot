"""Self-service data export.

Returns a single JSON-serialisable dict containing every bank and every
cashback item the user owns. The shape is forward-compatible: callers
should only read the keys they recognise and keep going if more appear.

The output is intentionally portable — string-encoded Decimals so any
JSON consumer (browser, Python, Excel) round-trips without precision
loss; ISO-8601 timestamps with a trailing ``Z``; explicit
``schema_version`` so future changes can break compatibility safely.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.models import CashbackDraftItem

SCHEMA_VERSION = 1


@dataclass(slots=True)
class ExportedItem:
    raw_category: str
    normalized_category: str
    percent: str
    source_type: str
    monthly_limit: str | None


@dataclass(slots=True)
class ExportedBank:
    bank_name: str
    items: list[ExportedItem] = field(default_factory=list)


@dataclass(slots=True)
class ExportedUser:
    schema_version: int
    exported_at: str  # ISO-8601 UTC
    user: dict[str, Any]
    banks: list[ExportedBank]

    def to_dict(self) -> dict[str, Any]:
        # asdict over nested dataclasses gives us a clean, json.dumps-able tree.
        return asdict(self)


class ExportUserDataUseCase:
    """Read all banks + cashback items belonging to ``user_id`` and shape
    them into a stable export DTO. Pure read — never writes."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        # Tests can inject a deterministic clock; the default fires at call
        # time and stamps the export with the current UTC instant.
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(self, *, user_id: int) -> ExportedUser:
        async with self.uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                # An export without a user is meaningless; return an empty
                # envelope rather than raising — callers asked for a snapshot
                # and an empty one is still a valid answer.
                return ExportedUser(
                    schema_version=SCHEMA_VERSION,
                    exported_at=_format_utc(self._clock()),
                    user={"id": user_id, "display_name": None, "language": None},
                    banks=[],
                )
            banks = await uow.banks.list_for_user(user_id)
            exported_banks: list[ExportedBank] = []
            for bank in banks:
                items = await uow.cashback.list_for_bank(bank.id)
                exported_banks.append(
                    ExportedBank(
                        bank_name=bank.bank_name,
                        items=[_export_item(item) for item in items],
                    )
                )
            return ExportedUser(
                schema_version=SCHEMA_VERSION,
                exported_at=_format_utc(self._clock()),
                user={
                    "id": user.id,
                    "display_name": user.display_name,
                    "language": user.language,
                    "notifications_enabled": user.notifications_enabled,
                },
                banks=exported_banks,
            )


def _export_item(item: CashbackDraftItem) -> ExportedItem:
    return ExportedItem(
        raw_category=item.raw_category,
        normalized_category=item.normalized_category,
        # Decimals in JSON: stringify to preserve precision; consumers parse
        # back via Decimal() if they need arithmetic.
        percent=str(item.percent),
        source_type=item.source_type,
        monthly_limit=str(item.monthly_limit) if item.monthly_limit is not None else None,
    )


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
