from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def category_menu(category_name: str, bank_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Изменить %", callback_data=f"category:edit:{bank_id}:{category_name}")],
            [InlineKeyboardButton("Переименовать", callback_data=f"category:rename:{bank_id}:{category_name}")],
            [InlineKeyboardButton("Удалить", callback_data=f"category:delete:{bank_id}:{category_name}")],
            [InlineKeyboardButton("Назад", callback_data=f"bank:categories:{bank_id}")],
        ]
    )
