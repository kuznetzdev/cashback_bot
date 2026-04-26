from __future__ import annotations

from app.application.workflow.models import UserCommand, WorkflowState

INTERRUPTIBLE_COMMANDS = {
    "start",
    "open_home",
    "open_help",
    "open_add_bank",
    "open_my_banks",
    "open_top",
    "open_settings",
    "open_history",
    "cancel_flow",
}


def should_interrupt_navigation(state: WorkflowState, command: UserCommand) -> bool:
    if not has_active_draft(state):
        return False
    if command.name in {"continue_draft", "discard_draft_and_go", "save_draft_and_go", "save_bank"}:
        return False
    return command.name in INTERRUPTIBLE_COMMANDS


def has_active_draft(state: WorkflowState) -> bool:
    if state.draft_items:
        return True
    if state.pending_input_kind is not None:
        return True
    if state.selected_bank_id is not None:
        return True
    if bool((state.selected_bank_name or "").strip()):
        return True
    if state.editing_item_index is not None:
        return True
    return "pending_category" in state.temp_payload or "pending_slug" in state.temp_payload


def can_save_draft(state: WorkflowState) -> bool:
    bank_name = (state.selected_bank_name or "").strip()
    if not bank_name:
        return False
    if not state.draft_items:
        return False
    return all(item.percent > 0 for item in state.draft_items)


def set_interrupt_target(state: WorkflowState, command: UserCommand) -> None:
    state.temp_payload["interrupt_target_name"] = command.name
    state.temp_payload["interrupt_target_payload"] = dict(command.payload)


def take_interrupt_target(state: WorkflowState) -> UserCommand:
    target_name = peek_interrupt_target_name(state)
    raw_payload = state.temp_payload.pop("interrupt_target_payload", {})
    state.temp_payload.pop("interrupt_target_name", None)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    return UserCommand(name=target_name, payload=payload)


def peek_interrupt_target_name(state: WorkflowState) -> str:
    raw_name = state.temp_payload.get("interrupt_target_name")
    if isinstance(raw_name, str) and raw_name:
        return raw_name
    return "open_home"


def clear_interrupt_target(state: WorkflowState) -> None:
    state.temp_payload.pop("interrupt_target_name", None)
    state.temp_payload.pop("interrupt_target_payload", None)
