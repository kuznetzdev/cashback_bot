from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.callback import nav


def settings_keyboard(localizer, language: str, notifications_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.language_ru"), callback_data=nav("set_lang", "ru"))
    builder.button(text=localizer.gettext(language, "buttons.language_en"), callback_data=nav("set_lang", "en"))
    toggle_key = "buttons.toggle_notifications_on" if notifications_enabled else "buttons.toggle_notifications_off"
    builder.button(text=localizer.gettext(language, toggle_key), callback_data=nav("toggle_notifications"))
    builder.button(text=localizer.gettext(language, "buttons.home"), callback_data=nav("home"))
    builder.adjust(2, 1, 1)
    return builder.as_markup()
