from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.schemas.cashback_item import DraftCashbackItem


class InputStates(StatesGroup):
    waiting_custom_bank_name = State()
    waiting_manual_lines = State()
    waiting_photo = State()
    waiting_item_category = State()
    waiting_item_percent = State()


async def get_draft_items(state: FSMContext) -> list[DraftCashbackItem]:
    data = await state.get_data()
    return [DraftCashbackItem.model_validate(item) for item in data.get("draft_items", [])]


async def set_draft_items(state: FSMContext, items: list[DraftCashbackItem]) -> None:
    await state.update_data(draft_items=[item.model_dump(mode="json") for item in items])


async def clear_flow_data(state: FSMContext) -> None:
    data = await state.get_data()
    last_screen_message_id = data.get("last_screen_message_id")
    await state.clear()
    if last_screen_message_id is not None:
        await state.update_data(last_screen_message_id=last_screen_message_id)
