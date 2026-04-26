from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.application.presenters import workflow_screens
from app.application.workflow import interrupts
from app.application.workflow.dispatcher import WorkflowDispatcher
from app.application.workflow.models import Screen, UserCommand, WorkflowResult, WorkflowState
from app.domain.models import CashbackDraftItem, UserAccount
from app.domain.services.categories import CategoryService


@dataclass(slots=True)
class StubDependencies:
    categories: CategoryService


def _result(user: UserAccount, state: WorkflowState, screen_id: str) -> WorkflowResult:
    return workflow_screens.result_with_screen(
        user=user,
        state=state,
        screen=Screen(id=screen_id, title_key=screen_id, body_key=screen_id),
    )


@pytest.mark.asyncio
async def test_dispatcher_routes_command_family_to_banks_before_navigation(monkeypatch) -> None:
    calls: list[str] = []
    user = UserAccount(id=1, display_name="Demo", language="ru", notifications_enabled=True)
    state = WorkflowState()
    deps = StubDependencies(categories=CategoryService())
    dispatcher = WorkflowDispatcher(deps)

    async def fake_draft(_deps, _user, _state, _command):
        calls.append("draft")
        return None

    async def fake_banks(_deps, routed_user, routed_state, _command):
        calls.append("banks")
        return _result(routed_user, routed_state, "my_banks")

    async def fake_navigation(_deps, _user, _state, _command):
        calls.append("navigation")
        return None

    monkeypatch.setattr("app.application.workflow.draft.handle_command", fake_draft)
    monkeypatch.setattr("app.application.workflow.banks.handle_command", fake_banks)
    monkeypatch.setattr("app.application.workflow.navigation.handle_command", fake_navigation)

    result = await dispatcher.execute(user, state, UserCommand(name="open_my_banks"))

    assert result.screen.id == "my_banks"
    assert calls == ["draft", "banks"]


@pytest.mark.asyncio
async def test_dispatcher_routes_to_navigation_when_other_handlers_skip(monkeypatch) -> None:
    calls: list[str] = []
    user = UserAccount(id=1, display_name="Demo", language="ru", notifications_enabled=True)
    state = WorkflowState()
    deps = StubDependencies(categories=CategoryService())
    dispatcher = WorkflowDispatcher(deps)

    async def fake_draft(_deps, _user, _state, _command):
        calls.append("draft")
        return None

    async def fake_banks(_deps, _user, _state, _command):
        calls.append("banks")
        return None

    async def fake_navigation(_deps, routed_user, routed_state, _command):
        calls.append("navigation")
        return _result(routed_user, routed_state, "help")

    monkeypatch.setattr("app.application.workflow.draft.handle_command", fake_draft)
    monkeypatch.setattr("app.application.workflow.banks.handle_command", fake_banks)
    monkeypatch.setattr("app.application.workflow.navigation.handle_command", fake_navigation)

    result = await dispatcher.execute(user, state, UserCommand(name="open_help"))

    assert result.screen.id == "help"
    assert calls == ["draft", "banks", "navigation"]


@pytest.mark.asyncio
async def test_save_draft_and_go_processes_target_iteratively_without_recursive_reentry(monkeypatch) -> None:
    calls: list[str] = []
    user = UserAccount(id=1, display_name="Demo", language="ru", notifications_enabled=True)
    state = WorkflowState(
        selected_bank_name="T-Bank",
        draft_items=[
            CashbackDraftItem(
                raw_category="Fuel", normalized_category="fuel", percent=Decimal("5"), source_type="manual"
            )
        ],
    )
    interrupts.set_interrupt_target(state, UserCommand(name="open_home"))
    deps = StubDependencies(categories=CategoryService())
    dispatcher = WorkflowDispatcher(deps)

    async def fake_save_bank(_deps, _user_id, _state):
        calls.append("save_bank")
        return 11

    async def fake_draft(_deps, _user, _state, _command):
        calls.append("draft")
        return None

    async def fake_banks(_deps, _user, _state, _command):
        calls.append("banks")
        return None

    async def fake_navigation(_deps, routed_user, routed_state, command):
        calls.append(f"navigation:{command.name}")
        return _result(routed_user, routed_state, "home")

    async def fake_log_event(_deps, _user_id, action, _payload=None):
        calls.append(f"log:{action}")

    monkeypatch.setattr("app.application.workflow.draft.save_bank", fake_save_bank)
    monkeypatch.setattr("app.application.workflow.draft.handle_command", fake_draft)
    monkeypatch.setattr("app.application.workflow.banks.handle_command", fake_banks)
    monkeypatch.setattr("app.application.workflow.navigation.handle_command", fake_navigation)
    monkeypatch.setattr("app.application.workflow.dispatcher.log_workflow_event", fake_log_event)

    result = await dispatcher.execute(user, state, UserCommand(name="save_draft_and_go"))

    assert result.screen.id == "home"
    assert calls == ["save_bank", "log:draft_saved_via_interrupt", "draft", "banks", "navigation:open_home"]
    assert any(
        effect.kind == "show_status" and effect.payload["message_key"] == "messages.saved_bank"
        for effect in result.effects
    )
