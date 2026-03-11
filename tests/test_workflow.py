from __future__ import annotations

from app.application.models import UserCommand, UserContext, WorkflowState
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService


async def _build_use_cases(uow_factory, dummy_ocr):
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    sync = SyncTelegramUserUseCase(uow_factory, default_language="ru")
    handle = HandleCommandUseCase(
        uow_factory=uow_factory,
        parser=parser,
        categories=categories,
        ranking=ranking,
        ocr=dummy_ocr,
    )
    return sync, handle


async def _create_user(sync_use_case: SyncTelegramUserUseCase):
    return await sync_use_case.execute(
        UserContext(external_user_id=1001, username="demo", full_name="Demo User"),
        log_action="user_started",
    )


async def test_manual_add_flow_and_save(uow_factory, dummy_ocr, store) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    assert result.screen.id == "choose_bank"

    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    assert result.screen.id == "input_method"

    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))
    assert result.state.pending_input_kind == "manual_lines"

    result = await handle.execute(
        user,
        result.state,
        UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%\nRestaurants 7%"}),
    )
    assert result.screen.id == "preview"
    assert len(result.state.draft_items) == 2

    result = await handle.execute(user, result.state, UserCommand(name="save_bank"))
    assert result.screen.id == "bank_details"
    assert len(store.banks) == 1


async def test_edit_saved_bank_replaces_item_set_atomically(uow_factory, dummy_ocr, store) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(
        user,
        WorkflowState(selected_bank_name="T-Bank", draft_items=[]),
        UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}),
    )
    result = await handle.execute(user, result.state, UserCommand(name="save_bank"))
    bank_id = result.state.selected_bank_id
    assert bank_id is not None

    result = await handle.execute(user, result.state, UserCommand(name="edit_bank", payload={"id": bank_id}))
    result = await handle.execute(user, result.state, UserCommand(name="delete_item", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="add_item"))
    result = await handle.execute(user, result.state, UserCommand(name="submit_item_category", payload={"text": "Pharmacy"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_item_percent", payload={"text": "3"}))
    result = await handle.execute(user, result.state, UserCommand(name="save_bank"))

    saved_items = store.bank_items[bank_id]
    assert len(saved_items) == 1
    assert saved_items[0].normalized_category == "pharmacy"


async def test_draft_editing_actions_are_logged_and_save_returns_status_effect(uow_factory, dummy_ocr, store) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}))
    result = await handle.execute(user, result.state, UserCommand(name="add_item"))
    result = await handle.execute(user, result.state, UserCommand(name="submit_item_category", payload={"text": "Pharmacy"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_item_percent", payload={"text": "3"}))
    result = await handle.execute(user, result.state, UserCommand(name="delete_item", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="save_bank"))

    actions = [entry.action for entry in store.logs]
    assert "draft_loaded_manual" in actions
    assert "draft_item_add_started" in actions
    assert "draft_item_category_set" in actions
    assert "draft_item_added" in actions
    assert "draft_item_deleted" in actions
    assert any(effect.kind == "show_status" and effect.payload.get("message_key") == "messages.saved_bank" for effect in result.effects)


async def test_unknown_free_text_falls_back_to_help_screen(uow_factory, dummy_ocr) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(
        user,
        WorkflowState(),
        UserCommand(name="submit_text", payload={"text": "abracadabra"}),
    )
    assert result.screen.id == "help"
    assert any(effect.kind == "show_status" and effect.payload.get("message_key") == "errors.unknown_command" for effect in result.effects)


async def test_interrupt_navigation_requires_explicit_decision(uow_factory, dummy_ocr) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}))

    interrupted = await handle.execute(user, result.state, UserCommand(name="open_top"))
    assert interrupted.screen.id == "interrupt_flow"
    assert any(action.command == "continue_draft" for action in interrupted.screen.actions)
    assert any(action.command == "discard_draft_and_go" for action in interrupted.screen.actions)
    assert any(action.command == "save_draft_and_go" for action in interrupted.screen.actions)

    resumed = await handle.execute(user, interrupted.state, UserCommand(name="continue_draft"))
    assert resumed.screen.id == "preview"


async def test_interrupt_navigation_from_pending_input_without_items(uow_factory, dummy_ocr) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))

    interrupted = await handle.execute(user, result.state, UserCommand(name="open_home"))
    assert interrupted.screen.id == "interrupt_flow"
    assert any(action.command == "discard_draft_and_go" for action in interrupted.screen.actions)
    assert any(action.command == "continue_draft" for action in interrupted.screen.actions)
    assert all(action.command != "save_draft_and_go" for action in interrupted.screen.actions)

    discarded = await handle.execute(user, interrupted.state, UserCommand(name="discard_draft_and_go"))
    assert discarded.screen.id == "home"
    assert discarded.state.pending_input_kind is None
    assert discarded.state.selected_bank_name is None


async def test_interrupt_discard_goes_to_target_and_clears_draft(uow_factory, dummy_ocr) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}))
    interrupted = await handle.execute(user, result.state, UserCommand(name="open_home"))

    discarded = await handle.execute(user, interrupted.state, UserCommand(name="discard_draft_and_go"))
    assert discarded.screen.id == "home"
    assert any(effect.kind == "show_status" and effect.payload.get("message_key") == "messages.draft_discarded" for effect in discarded.effects)


async def test_interrupt_save_and_go_persists_bank(uow_factory, dummy_ocr, store) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}))
    interrupted = await handle.execute(user, result.state, UserCommand(name="open_my_banks"))
    saved = await handle.execute(user, interrupted.state, UserCommand(name="save_draft_and_go"))

    assert saved.screen.id == "my_banks"
    assert len(store.banks) == 1
