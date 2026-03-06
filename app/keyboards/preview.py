from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.schemas.cashback_item import DraftCashbackItem
from app.utils.callback import nav


def preview_keyboard(localizer, language: str, items: list[DraftCashbackItem]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, item in enumerate(items):
        label = f"{index + 1}. {item.raw_category} ({item.percent}%)"
        builder.button(text=label, callback_data=nav("edit_item", index))
    builder.button(text=localizer.gettext(language, "buttons.add_item"), callback_data=nav("add_item"))
    builder.button(text=localizer.gettext(language, "buttons.save"), callback_data=nav("save_bank"))
    builder.button(text=localizer.gettext(language, "buttons.cancel"), callback_data=nav("cancel_add"))
    builder.adjust(1)
    return builder.as_markup()


def edit_item_keyboard(localizer, language: str, index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.edit_category"), callback_data=nav("edit_item_category", index))
    builder.button(text=localizer.gettext(language, "buttons.edit_percent"), callback_data=nav("edit_item_percent", index))
    builder.button(text=localizer.gettext(language, "buttons.delete"), callback_data=nav("delete_item", index))
    builder.button(text=localizer.gettext(language, "buttons.back"), callback_data=nav("preview"))
    builder.adjust(1)
    return builder.as_markup()
