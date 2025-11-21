from __future__ import annotations

"""Start and menu handlers."""
from telegram import Update
from telegram.ext import ContextTypes

from ..i18n import Translator
from ..keyboards.main_menu import main_menu_keyboard


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    settings = context.application.bot_data["settings"]
    locale = settings.locale
    await update.message.reply_text(
        translator.translate("start_message", locale),
        reply_markup=main_menu_keyboard(translator, locale),
    )
