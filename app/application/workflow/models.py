from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import CashbackDraftItem, UserAccount


@dataclass(slots=True)
class UserCommand:
    name: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Action:
    command: str
    label_key: str
    payload: dict[str, object] = field(default_factory=dict)
    destructive: bool = False
    variant: str = "secondary"
    group: str | None = None


@dataclass(slots=True)
class Screen:
    id: str
    title_key: str
    body_key: str
    body_params: dict[str, object] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    expects_input: str | None = None
    layout_hint: str = "default"


@dataclass(slots=True)
class Effect:
    kind: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowState:
    mode: str | None = None
    selected_bank_id: int | None = None
    selected_bank_name: str | None = None
    draft_items: list[CashbackDraftItem] = field(default_factory=list)
    editing_item_index: int | None = None
    pending_input_kind: str | None = None
    temp_payload: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "selected_bank_id": self.selected_bank_id,
            "selected_bank_name": self.selected_bank_name,
            "draft_items": [self._serialize_item(item) for item in self.draft_items],
            "editing_item_index": self.editing_item_index,
            "pending_input_kind": self.pending_input_kind,
            "temp_payload": dict(self.temp_payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "WorkflowState":
        from decimal import Decimal

        raw_items = data.get("draft_items", [])
        if not isinstance(raw_items, list):
            raw_items = []
        items = [
            CashbackDraftItem(
                raw_category=str(item.get("raw_category", "")),
                normalized_category=str(item.get("normalized_category", "")),
                percent=Decimal(str(item.get("percent", "0"))),
                source_type=str(item.get("source_type", "")),
            )
            for item in raw_items
            if isinstance(item, dict)
        ]
        raw_temp_payload = data.get("temp_payload", {})
        if not isinstance(raw_temp_payload, dict):
            raw_temp_payload = {}
        return cls(
            mode=_as_str_or_none(data.get("mode")),
            selected_bank_id=_as_int_or_none(data.get("selected_bank_id")),
            selected_bank_name=_as_str_or_none(data.get("selected_bank_name")),
            draft_items=items,
            editing_item_index=_as_int_or_none(data.get("editing_item_index")),
            pending_input_kind=_as_str_or_none(data.get("pending_input_kind")),
            temp_payload=dict(raw_temp_payload),
        )

    @staticmethod
    def _serialize_item(item: CashbackDraftItem) -> dict[str, object]:
        return {
            "raw_category": item.raw_category,
            "normalized_category": item.normalized_category,
            "percent": str(item.percent),
            "source_type": item.source_type,
        }


@dataclass(slots=True)
class WorkflowResult:
    user: UserAccount
    state: WorkflowState
    screen: Screen
    effects: list[Effect] = field(default_factory=list)


def _as_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _as_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
