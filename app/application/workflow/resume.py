from __future__ import annotations

from app.application.presenters import workflow_screens
from app.application.presenters.workflow_formatters import target_label
from app.application.workflow.dependencies import WorkflowDependencies
from app.application.workflow.interrupts import can_save_draft, has_active_draft, peek_interrupt_target_name
from app.application.workflow.models import WorkflowResult, WorkflowState
from app.domain.models import UserAccount


async def resume_workflow(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
) -> WorkflowResult:
    if not has_active_draft(state):
        return workflow_screens.result_with_screen(user=user, state=WorkflowState(), screen=workflow_screens.home_screen())

    if "interrupt_target_name" in state.temp_payload:
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.interrupt_screen(
                target_label_key=target_label(peek_interrupt_target_name(state)),
                can_save=can_save_draft(state),
            ),
        )

    if state.pending_input_kind == "custom_bank_name":
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.custom_bank_prompt_screen())
    if state.pending_input_kind == "manual_lines":
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.manual_prompt_screen())
    if state.pending_input_kind == "photo_upload":
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.photo_prompt_screen())
    if state.pending_input_kind in {"item_category_new", "item_category_edit"}:
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.item_category_prompt_screen())
    if state.pending_input_kind in {"item_percent_new", "item_percent_edit"}:
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.item_percent_prompt_screen())

    if state.draft_items:
        if state.selected_bank_name:
            return workflow_screens.result_with_screen(
                user=user,
                state=state,
                screen=workflow_screens.preview_screen(state, user.language, deps.categories),
            )
        existing_banks = await deps.get_user_banks_use_case.execute(user_id=user.id)
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.choose_bank_screen(
                existing_banks=existing_banks,
                popular_banks=list(deps.popular_banks),
                has_draft=True,
                target_month=state.target_month,
            ),
        )

    if state.selected_bank_name:
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.input_method_screen(state.selected_bank_name, state.target_month),
        )

    return workflow_screens.result_with_screen(user=user, state=WorkflowState(), screen=workflow_screens.home_screen())
