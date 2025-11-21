from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..services.categories import CategoryService
from ..services.storage import StorageService


async def handle_delete(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    categories_service: CategoryService = context.application.bot_data["categories"]
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 3:
        return
    _, action, raw_id = parts[:3]
    bank_id = int(raw_id)
    if action == "delete":
        await storage.delete_bank(bank_id)
        await query.edit_message_text("Банк удалён")
    elif action == "categories" and len(parts) >= 4:
        category_name = parts[3]
        banks = await storage.list_banks(context.user_data.get("user_id"))
        bank = next((b for b in banks if b.id == bank_id), None)
        if not bank:
            await query.edit_message_text("Банк не найден")
            return
        updated = categories_service.soft_delete(bank.categories, category_name)
        await storage.update_bank_categories(bank_id, updated)
        await query.edit_message_text("Категория помечена как удалённая")
