from __future__ import annotations

from aiogram.fsm.context import FSMContext

from app.application.models import WorkflowState

KEY_WORKFLOW = "workflow_state"
KEY_LAST_SCREEN_ID = "last_screen_message_id"


async def load_workflow_state(state: FSMContext) -> WorkflowState:
    data = await state.get_data()
    raw = data.get(KEY_WORKFLOW)
    if isinstance(raw, dict):
        return WorkflowState.from_dict(raw)
    return WorkflowState()


async def save_workflow_state(state: FSMContext, workflow: WorkflowState) -> None:
    await state.update_data(**{KEY_WORKFLOW: workflow.to_dict()})


async def load_last_screen_message_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    value = data.get(KEY_LAST_SCREEN_ID)
    if isinstance(value, int):
        return value
    return None


async def save_last_screen_message_id(state: FSMContext, message_id: int | None) -> None:
    await state.update_data(**{KEY_LAST_SCREEN_ID: message_id})
