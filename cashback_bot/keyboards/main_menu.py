from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard(translator, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(translator.translate("btn_add_bank", locale), callback_data="nav:add_bank")],
            [InlineKeyboardButton(translator.translate("btn_import_photo", locale), callback_data="nav:import")],
            [InlineKeyboardButton(translator.translate("btn_show_global_rating", locale), callback_data="nav:ranking")],
            [InlineKeyboardButton(translator.translate("btn_settings", locale), callback_data="nav:settings")],
        ]
    )
