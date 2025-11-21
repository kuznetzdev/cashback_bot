from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_menu(ok_action: str, cancel_action: str = "nav:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сохранить", callback_data=ok_action)],
            [InlineKeyboardButton("Отмена", callback_data=cancel_action)],
        ]
    )
