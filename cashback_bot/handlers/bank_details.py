from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..keyboards.bank_menu import bank_menu
from ..services.storage import StorageService


async def handle_bank_details(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    banks = await storage.list_banks(user_id)
    if not banks:
        await update.effective_message.reply_text("Банки не найдены")
        return
    for bank in banks:
        text = f"Банк: {bank.name}\nКатегорий: {len(bank.categories)}"
        await update.effective_message.reply_text(text, reply_markup=bank_menu(bank.id))
