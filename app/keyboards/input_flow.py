from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.callback import nav


def input_method_keyboard(localizer, language: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.input_photo"), callback_data=nav("input_photo"))
    builder.button(text=localizer.gettext(language, "buttons.input_manual"), callback_data=nav("input_manual"))
    builder.button(text=localizer.gettext(language, "buttons.input_template"), callback_data=nav("input_template"))
    builder.button(text=localizer.gettext(language, "buttons.cancel"), callback_data=nav("cancel_add"))
    builder.adjust(1)
    return builder.as_markup()
