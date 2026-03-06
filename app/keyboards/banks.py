from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.constants import POPULAR_BANKS
from app.utils.callback import nav


def choose_bank_keyboard(localizer, language: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, bank_name in enumerate(POPULAR_BANKS):
        builder.button(text=bank_name, callback_data=nav("add_bank_select", index))
    builder.button(text=localizer.gettext(language, "buttons.other_bank"), callback_data=nav("add_bank_other"))
    builder.button(text=localizer.gettext(language, "buttons.home"), callback_data=nav("home"))
    builder.adjust(1)
    return builder.as_markup()


def my_banks_keyboard(localizer, language: str, banks: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for bank in banks:
        builder.button(text=bank.bank_name, callback_data=nav("bank", bank.id))
    builder.button(text=localizer.gettext(language, "buttons.home"), callback_data=nav("home"))
    builder.adjust(1)
    return builder.as_markup()


def bank_details_keyboard(localizer, language: str, bank_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.edit"), callback_data=nav("edit_bank", bank_id))
    builder.button(text=localizer.gettext(language, "buttons.delete"), callback_data=nav("delete_bank", bank_id))
    builder.button(text=localizer.gettext(language, "buttons.home"), callback_data=nav("home"))
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_bank_keyboard(localizer, language: str, bank_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=localizer.gettext(language, "buttons.confirm_delete"), callback_data=nav("confirm_delete_bank", bank_id))
    builder.button(text=localizer.gettext(language, "buttons.back"), callback_data=nav("bank", bank_id))
    builder.adjust(1)
    return builder.as_markup()
