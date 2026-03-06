from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.callback import nav


def history_keyboard(localizer, language: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.home"), callback_data=nav("home"))
    return builder.as_markup()
