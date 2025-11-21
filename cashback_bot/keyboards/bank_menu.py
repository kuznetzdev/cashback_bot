from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def bank_menu(bank_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Предпросмотр", callback_data=f"bank:preview:{bank_id}")],
            [InlineKeyboardButton("Удалить", callback_data=f"bank:delete:{bank_id}")],
            [InlineKeyboardButton("Категории", callback_data=f"bank:categories:{bank_id}")],
        ]
    )
