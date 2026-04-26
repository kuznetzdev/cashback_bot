from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.application.presenters import workflow_screens
from app.application.workflow.dependencies import WorkflowDependencies, log_workflow_event
from app.application.workflow.models import UserCommand, WorkflowResult, WorkflowState
from app.domain.enums import SourceType
from app.domain.errors import ValidationError
from app.domain.models import CashbackDraftItem, UserAccount

DRAFT_COMMANDS = {
    "open_add_bank",
    "select_bank_preset",
    "select_bank_other",
    "submit_custom_bank_name",
    "choose_input_method",
    "submit_manual_text",
    "submit_uploaded_image",
    "open_preview",
    "add_item",
    "pick_item",
    "edit_item_category",
    "edit_item_percent",
    "delete_item",
    "submit_item_category",
    "submit_item_percent",
}


async def handle_command(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
    command: UserCommand,
) -> WorkflowResult | None:
    name = command.name
    if name == "open_add_bank":
        return workflow_screens.result_with_screen(
            user=user,
            state=WorkflowState(mode="create"),
            screen=workflow_screens.choose_bank_screen(list(deps.popular_banks)),
        )
    if name == "select_bank_preset":
        index = int(command.payload["index"])
        if index < 0 or index >= len(deps.popular_banks):
            raise ValidationError("errors.invalid_bank_name")
        state.selected_bank_name = deps.popular_banks[index]
        state.selected_bank_id = None
        state.pending_input_kind = None
        state.temp_payload = {}
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.input_method_screen(state.selected_bank_name),
        )
    if name == "select_bank_other":
        state.pending_input_kind = "custom_bank_name"
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.custom_bank_prompt_screen()
        )
    if name == "submit_custom_bank_name":
        bank_name = str(command.payload["text"]).strip()
        if not bank_name:
            raise ValidationError("errors.invalid_bank_name")
        state.selected_bank_name = bank_name
        state.selected_bank_id = None
        state.pending_input_kind = None
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.input_method_screen(bank_name)
        )
    if name == "choose_input_method":
        method = str(command.payload["method"])
        if method == "manual":
            state.pending_input_kind = "manual_lines"
            state.temp_payload["source_type"] = SourceType.MANUAL.value
            await log_workflow_event(deps, user.id, "input_method_selected", {"method": "manual"})
            return workflow_screens.result_with_screen(
                user=user, state=state, screen=workflow_screens.manual_prompt_screen()
            )
        if method == "photo":
            state.pending_input_kind = "photo_upload"
            state.temp_payload["source_type"] = SourceType.OCR.value
            await log_workflow_event(deps, user.id, "input_method_selected", {"method": "photo"})
            return workflow_screens.result_with_screen(
                user=user, state=state, screen=workflow_screens.photo_prompt_screen()
            )
        if method == "template":
            state.pending_input_kind = None
            state.temp_payload["source_type"] = SourceType.TEMPLATE.value
            state.draft_items = [
                CashbackDraftItem(
                    raw_category=deps.categories.display_name(slug, user.language),
                    normalized_category=slug,
                    percent=Decimal("0"),
                    source_type=SourceType.TEMPLATE.value,
                )
                for slug in deps.categories.template_slugs()
            ]
            await log_workflow_event(
                deps, user.id, "draft_loaded_template", {"items_count": len(state.draft_items)}
            )
            return workflow_screens.result_with_screen(
                user=user,
                state=state,
                screen=workflow_screens.preview_screen(state, user.language, deps.categories),
            )
        raise ValidationError("errors.send_photo_or_text")
    if name == "submit_manual_text":
        state.draft_items = deps.parse_manual_use_case.execute(str(command.payload["text"]))
        state.pending_input_kind = None
        await log_workflow_event(
            deps, user.id, "draft_loaded_manual", {"items_count": len(state.draft_items)}
        )
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.preview_screen(state, user.language, deps.categories),
        )
    if name == "submit_uploaded_image":
        upload_obj = command.payload.get("upload")
        if upload_obj is None:
            raise ValidationError("errors.broken_image")
        state.draft_items = await deps.process_uploaded_image_use_case.execute(upload_obj)
        state.pending_input_kind = None
        await log_workflow_event(deps, user.id, "draft_loaded_ocr", {"items_count": len(state.draft_items)})
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.preview_screen(state, user.language, deps.categories),
        )
    if name == "open_preview":
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.preview_screen(state, user.language, deps.categories),
        )
    if name == "add_item":
        state.pending_input_kind = "item_category_new"
        await log_workflow_event(
            deps, user.id, "draft_item_add_started", {"items_count": len(state.draft_items)}
        )
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.item_category_prompt_screen()
        )
    if name == "pick_item":
        idx = int(command.payload["index"])
        if idx < 0 or idx >= len(state.draft_items):
            raise ValidationError("errors.invalid_manual_input")
        state.editing_item_index = idx
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.edit_item_screen(state.draft_items[idx], idx),
        )
    if name == "edit_item_category":
        state.pending_input_kind = "item_category_edit"
        state.editing_item_index = int(command.payload["index"])
        await log_workflow_event(
            deps, user.id, "draft_item_edit_category_started", {"index": state.editing_item_index}
        )
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.item_category_prompt_screen()
        )
    if name == "edit_item_percent":
        state.pending_input_kind = "item_percent_edit"
        state.editing_item_index = int(command.payload["index"])
        await log_workflow_event(
            deps, user.id, "draft_item_edit_percent_started", {"index": state.editing_item_index}
        )
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.item_percent_prompt_screen()
        )
    if name == "delete_item":
        idx = int(command.payload["index"])
        if idx < 0 or idx >= len(state.draft_items):
            raise ValidationError("errors.invalid_manual_input")
        state.draft_items.pop(idx)
        await log_workflow_event(
            deps,
            user.id,
            "draft_item_deleted",
            {"index": idx, "remaining_items_count": len(state.draft_items)},
        )
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.preview_screen(state, user.language, deps.categories),
        )
    if name == "submit_item_category":
        return await _submit_item_category(deps, user, state, str(command.payload["text"]))
    if name == "submit_item_percent":
        return await _submit_item_percent(deps, user, state, str(command.payload["text"]))
    return None


async def save_bank(deps: WorkflowDependencies, user_id: int, state: WorkflowState) -> int:
    bank_id = await deps.save_bank_draft_use_case.execute(
        user_id=user_id,
        bank_id=state.selected_bank_id,
        bank_name=state.selected_bank_name or "",
        items=state.draft_items,
    )
    state.selected_bank_id = bank_id
    state.pending_input_kind = None
    return bank_id


async def _submit_item_category(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
    text: str,
) -> WorkflowResult:
    value = text.strip()
    if not value:
        raise ValidationError("errors.invalid_manual_input")
    normalized = deps.categories.normalize(value)
    if state.pending_input_kind == "item_category_edit":
        idx = state.editing_item_index
        if idx is None or idx >= len(state.draft_items):
            raise ValidationError("errors.invalid_manual_input")
        old = state.draft_items[idx]
        state.draft_items[idx] = CashbackDraftItem(
            raw_category=value,
            normalized_category=normalized.slug,
            percent=old.percent,
            source_type=old.source_type,
        )
        await log_workflow_event(
            deps,
            user.id,
            "draft_item_category_set",
            {"mode": "edit", "index": idx, "normalized_category": normalized.slug},
        )
        state.pending_input_kind = None
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.preview_screen(state, user.language, deps.categories),
        )
    state.temp_payload["pending_category"] = value
    state.temp_payload["pending_slug"] = normalized.slug
    await log_workflow_event(
        deps,
        user.id,
        "draft_item_category_set",
        {"mode": "new_pending", "normalized_category": normalized.slug},
    )
    state.pending_input_kind = "item_percent_new"
    return workflow_screens.result_with_screen(
        user=user, state=state, screen=workflow_screens.item_percent_prompt_screen()
    )


async def _submit_item_percent(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
    text: str,
) -> WorkflowResult:
    percent = _parse_percent(text)
    if state.pending_input_kind == "item_percent_edit":
        idx = state.editing_item_index
        if idx is None or idx >= len(state.draft_items):
            raise ValidationError("errors.invalid_percent")
        old = state.draft_items[idx]
        state.draft_items[idx] = CashbackDraftItem(
            raw_category=old.raw_category,
            normalized_category=old.normalized_category,
            percent=percent,
            source_type=old.source_type,
        )
        await log_workflow_event(
            deps, user.id, "draft_item_percent_set", {"mode": "edit", "index": idx, "percent": str(percent)}
        )
    else:
        category = state.temp_payload.get("pending_category")
        slug = state.temp_payload.get("pending_slug")
        source_type = state.temp_payload.get("source_type", SourceType.MANUAL.value)
        if not category or not slug:
            raise ValidationError("errors.invalid_manual_input")
        state.draft_items.append(
            CashbackDraftItem(
                raw_category=str(category),
                normalized_category=str(slug),
                percent=percent,
                source_type=str(source_type),
            )
        )
        await log_workflow_event(
            deps, user.id, "draft_item_added", {"normalized_category": str(slug), "percent": str(percent)}
        )
        state.temp_payload.pop("pending_category", None)
        state.temp_payload.pop("pending_slug", None)
    state.pending_input_kind = None
    return workflow_screens.result_with_screen(
        user=user,
        state=state,
        screen=workflow_screens.preview_screen(state, user.language, deps.categories),
    )


def _parse_percent(value: str) -> Decimal:
    try:
        percent = Decimal(value.strip().replace(",", "."))
    except InvalidOperation as error:
        raise ValidationError("errors.invalid_percent") from error
    if percent <= 0 or percent > 100:
        raise ValidationError("errors.invalid_percent")
    return percent.quantize(Decimal("0.01"))
