from __future__ import annotations

from decimal import Decimal

from app.application.workflow import interrupts
from app.application.workflow.models import UserCommand, WorkflowState
from app.domain.models import CashbackDraftItem


def test_has_active_draft_and_can_save_draft_follow_state_contents() -> None:
    empty = WorkflowState()
    pending = WorkflowState(selected_bank_name="T-Bank", pending_input_kind="manual_lines")
    filled = WorkflowState(
        selected_bank_name="T-Bank",
        draft_items=[
            CashbackDraftItem(
                raw_category="Fuel", normalized_category="fuel", percent=Decimal("5"), source_type="manual"
            )
        ],
    )

    assert interrupts.has_active_draft(empty) is False
    assert interrupts.has_active_draft(pending) is True
    assert interrupts.has_active_draft(filled) is True
    assert interrupts.can_save_draft(empty) is False
    assert interrupts.can_save_draft(pending) is False
    assert interrupts.can_save_draft(filled) is True


def test_interrupt_target_lifecycle_roundtrip() -> None:
    state = WorkflowState()
    target = UserCommand(name="open_home")

    interrupts.set_interrupt_target(state, target)
    assert interrupts.peek_interrupt_target_name(state) == "open_home"
    assert interrupts.take_interrupt_target(state).name == "open_home"
    assert interrupts.peek_interrupt_target_name(state) == "open_home"

    interrupts.clear_interrupt_target(state)
    assert interrupts.peek_interrupt_target_name(state) == "open_home"


def test_should_interrupt_navigation_only_for_navigation_commands_with_active_draft() -> None:
    state = WorkflowState(selected_bank_name="T-Bank", pending_input_kind="manual_lines")

    assert interrupts.should_interrupt_navigation(state, UserCommand(name="open_home")) is True
    assert interrupts.should_interrupt_navigation(state, UserCommand(name="open_top")) is True
    assert interrupts.should_interrupt_navigation(state, UserCommand(name="continue_draft")) is False
    assert interrupts.should_interrupt_navigation(state, UserCommand(name="save_bank")) is False
    assert interrupts.should_interrupt_navigation(WorkflowState(), UserCommand(name="open_home")) is False
