from __future__ import annotations

from app.application.auth.models import ExternalIdentityContext
from app.application.auth.use_cases import AuthenticateExternalIdentityUseCase
from app.application.dto.media import ImageUpload
from app.application.workflow.models import UserCommand, WorkflowState
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.months import current_month_key, shift_month_key
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService


async def _build_use_cases(uow_factory, dummy_ocr):
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    authenticate_external_identity = AuthenticateExternalIdentityUseCase(uow_factory, default_language="ru")
    handle = HandleCommandUseCase(
        uow_factory=uow_factory,
        parser=parser,
        categories=categories,
        ranking=ranking,
        ocr=dummy_ocr,
    )
    return authenticate_external_identity, handle


async def _create_user(authenticate_external_identity_use_case: AuthenticateExternalIdentityUseCase):
    return await authenticate_external_identity_use_case.execute(
        ExternalIdentityContext(
            provider="telegram",
            provider_user_id="1001",
            provider_username="demo",
            provider_display_name="Demo User",
        ),
        create_user_if_missing=True,
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
    bank_id = next(iter(store.banks))
    assert bank_id is not None

    result = await handle.execute(user, result.state, UserCommand(name="edit_bank", payload={"id": bank_id}))
    result = await handle.execute(user, result.state, UserCommand(name="delete_item", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="add_item"))
    result = await handle.execute(user, result.state, UserCommand(name="submit_item_category", payload={"text": "Pharmacy"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_item_percent", payload={"text": "3"}))
    result = await handle.execute(user, result.state, UserCommand(name="save_bank"))

    saved_items = store.bank_items[bank_id][current_month_key()]
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


async def test_uploaded_image_auto_selects_single_existing_bank_and_opens_preview(uow_factory, dummy_ocr, store) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    initial = await handle.execute(
        user,
        WorkflowState(selected_bank_name="T-Bank"),
        UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}),
    )
    saved = await handle.execute(user, initial.state, UserCommand(name="save_bank"))
    saved_bank_id = next(iter(store.banks))

    dummy_ocr.value = "Taxi 3%\nRestaurants 7%"
    result = await handle.execute(
        user,
        WorkflowState(),
        UserCommand(
            name="submit_uploaded_image",
            payload={
                "upload": ImageUpload(
                    content=b"fake-image",
                    filename="screen.png",
                    content_type="image/png",
                )
            },
        ),
    )

    assert result.screen.id == "preview"
    assert result.state.selected_bank_id == saved_bank_id
    assert result.state.selected_bank_name == "T-Bank"
    assert [item.normalized_category for item in result.state.draft_items] == ["restaurants", "taxi"]


async def test_month_snapshots_are_saved_separately_for_same_bank(uow_factory, dummy_ocr, store) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)
    current_month = current_month_key()
    next_month = shift_month_key(current_month, 1)

    first_result = await handle.execute(
        user,
        WorkflowState(selected_bank_name="T-Bank", target_month=current_month),
        UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}),
    )
    first_saved = await handle.execute(user, first_result.state, UserCommand(name="save_bank"))
    bank_id = next(iter(store.banks))
    assert bank_id is not None

    second_result = await handle.execute(
        user,
        WorkflowState(selected_bank_id=bank_id, selected_bank_name="T-Bank", target_month=next_month),
        UserCommand(name="submit_manual_text", payload={"text": "Restaurants 7%"}),
    )
    await handle.execute(user, second_result.state, UserCommand(name="save_bank"))

    assert [item.normalized_category for item in store.bank_items[bank_id][current_month]] == ["fuel"]
    assert [item.normalized_category for item in store.bank_items[bank_id][next_month]] == ["restaurants"]


async def test_save_bank_clears_active_draft_state(uow_factory, dummy_ocr) -> None:
    sync, handle = await _build_use_cases(uow_factory, dummy_ocr)
    user = await _create_user(sync)

    result = await handle.execute(user, WorkflowState(), UserCommand(name="open_add_bank"))
    result = await handle.execute(user, result.state, UserCommand(name="select_bank_preset", payload={"index": 0}))
    result = await handle.execute(user, result.state, UserCommand(name="choose_input_method", payload={"method": "manual"}))
    result = await handle.execute(user, result.state, UserCommand(name="submit_manual_text", payload={"text": "Fuel 5%"}))

    saved = await handle.execute(user, result.state, UserCommand(name="save_bank"))

    assert saved.screen.id == "bank_details"
    assert saved.state == WorkflowState()

    home = await handle.execute(user, saved.state, UserCommand(name="open_home"))
    assert home.screen.id == "home"
