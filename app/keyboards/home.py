from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.callback import nav


def home_keyboard(localizer, language: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.add_bank"), callback_data=nav("add_bank"))
    builder.button(text=localizer.gettext(language, "buttons.my_banks"), callback_data=nav("my_banks"))
    builder.button(text=localizer.gettext(language, "buttons.top"), callback_data=nav("top"))
    builder.button(text=localizer.gettext(language, "buttons.settings"), callback_data=nav("settings"))
    builder.button(text=localizer.gettext(language, "buttons.history"), callback_data=nav("history"))
    builder.button(text=localizer.gettext(language, "buttons.help"), callback_data=nav("help"))
    builder.adjust(1)
    return builder.as_markup()
