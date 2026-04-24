from __future__ import annotations

from app.application.presenters import workflow_screens
from app.application.workflow import banks
from app.application.workflow.models import Effect, UserCommand, WorkflowResult, WorkflowState
from app.application.workflow.dependencies import WorkflowDependencies
from app.domain.errors import ValidationError
from app.domain.models import UserAccount


async def route_text(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
    text: str,
) -> UserCommand | WorkflowResult:
    kind = state.pending_input_kind
    if kind == "custom_bank_name":
        return UserCommand(name="submit_custom_bank_name", payload={"text": text})
    if kind == "manual_lines":
        return UserCommand(name="submit_manual_text", payload={"text": text})
    if kind in {"item_category_new", "item_category_edit"}:
        return UserCommand(name="submit_item_category", payload={"text": text})
    if kind in {"item_percent_new", "item_percent_edit"}:
        return UserCommand(name="submit_item_percent", payload={"text": text})
    best_intent = deps.parser.understand_best_query(text)
    if best_intent:
        return UserCommand(name="open_top_category", payload={"slug": best_intent.normalized_category})
    delete_intent = deps.parser.understand_delete_command(text)
    if delete_intent:
        if delete_intent.kind == "bank":
            await banks.delete_bank_by_name(deps, user.id, delete_intent.target)
            return workflow_screens.result_with_screen(
                user=user,
                state=WorkflowState(),
                screen=workflow_screens.home_screen(body_key="messages.deleted_bank"),
            )
        deleted_count, touched_banks = await deps.delete_category_use_case.execute(user_id=user.id, query=delete_intent.target)
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.delete_category_result_screen(deleted_count, touched_banks),
        )
    try:
        deps.parse_manual_use_case.execute(text)
    except ValidationError:
        pass
    else:
        return UserCommand(name="submit_manual_text", payload={"text": text})
    return workflow_screens.result_with_screen(
        user=user,
        state=state,
        screen=workflow_screens.help_screen(),
        effects=[Effect(kind="show_status", payload={"message_key": "errors.unknown_command"})],
    )
