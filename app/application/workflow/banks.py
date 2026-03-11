from __future__ import annotations

from rapidfuzz import process

from app.application.presenters import workflow_screens
from app.application.workflow.dependencies import WorkflowDependencies
from app.application.workflow.models import UserCommand, WorkflowResult, WorkflowState
from app.domain.errors import NotFoundError
from app.domain.models import UserAccount


async def handle_command(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
    command: UserCommand,
) -> WorkflowResult | None:
    name = command.name
    if name == "open_my_banks":
        banks = await deps.get_user_banks_use_case.execute(user_id=user.id)
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.my_banks_screen(banks))
    if name == "open_bank":
        aggregate = await load_bank_aggregate(deps, user.id, int(command.payload["id"]))
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.bank_details_screen(aggregate, user.language, deps.categories),
        )
    if name == "edit_bank":
        aggregate = await load_bank_aggregate(deps, user.id, int(command.payload["id"]))
        state.mode = "edit"
        state.selected_bank_id = aggregate.bank.id
        state.selected_bank_name = aggregate.bank.bank_name
        state.draft_items = aggregate.items
        state.pending_input_kind = None
        if aggregate.items:
            state.temp_payload["source_type"] = aggregate.items[0].source_type
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.preview_screen(state, user.language, deps.categories),
        )
    if name == "request_delete_bank":
        aggregate = await load_bank_aggregate(deps, user.id, int(command.payload["id"]))
        return workflow_screens.result_with_screen(user=user, state=state, screen=workflow_screens.confirm_delete_bank_screen(aggregate))
    if name == "confirm_delete_bank":
        await deps.delete_bank_use_case.execute(user_id=user.id, bank_id=int(command.payload["id"]))
        return workflow_screens.result_with_screen(
            user=user,
            state=WorkflowState(),
            screen=workflow_screens.home_screen(body_key="messages.deleted_bank"),
        )
    return None


async def load_bank_aggregate(deps: WorkflowDependencies, user_id: int, bank_id: int):
    return await deps.get_bank_details_use_case.execute(user_id=user_id, bank_id=bank_id)


async def delete_bank_by_name(deps: WorkflowDependencies, user_id: int, bank_name: str) -> None:
    banks = await deps.get_user_banks_use_case.execute(user_id=user_id)
    if not banks:
        raise NotFoundError("errors.bank_not_found")
    matched = process.extractOne(bank_name, [item.bank_name for item in banks], score_cutoff=70)
    if not matched:
        raise NotFoundError("errors.bank_not_found")
    bank = next(item for item in banks if item.bank_name == matched[0])
    await deps.delete_bank_use_case.execute(user_id=user_id, bank_id=bank.id)
