from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..i18n import Translator
from ..keyboards.main_menu import main_menu_keyboard


async def handle_menu(update: Update, context: CallbackContext) -> None:
    translator: Translator = context.application.bot_data["translator"]
    settings = context.application.bot_data["settings"]
    locale = settings.locale
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            translator.translate("main_menu_title", locale),
            reply_markup=main_menu_keyboard(translator, locale),
        )
    else:
        await update.message.reply_text(
            translator.translate("main_menu_title", locale),
            reply_markup=main_menu_keyboard(translator, locale),
        )
