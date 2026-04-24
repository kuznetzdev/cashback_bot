from __future__ import annotations

from aiogram.fsm.context import FSMContext

KEY_LAST_SCREEN_ID = "last_screen_message_id"


async def load_last_screen_message_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    value = data.get(KEY_LAST_SCREEN_ID)
    if isinstance(value, int):
        return value
    return None


async def save_last_screen_message_id(state: FSMContext, message_id: int | None) -> None:
    await state.update_data(**{KEY_LAST_SCREEN_ID: message_id})
