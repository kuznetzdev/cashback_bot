from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.callback import nav


def top_keyboard(localizer, language: str, category_slugs: list[str], category_labels: dict[str, str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slug in category_slugs:
        builder.button(text=category_labels[slug], callback_data=nav("top_category", slug))
    builder.button(text=localizer.gettext(language, "buttons.home"), callback_data=nav("home"))
    builder.adjust(1)
    return builder.as_markup()
