from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Уведомления ежедневно", callback_data="settings:daily")],
            [InlineKeyboardButton("Уведомления ежемесячно", callback_data="settings:monthly")],
            [InlineKeyboardButton("Назад", callback_data="nav:main")],
        ]
    )
