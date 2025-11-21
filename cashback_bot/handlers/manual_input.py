from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..models.bank import Bank, BankCategory
from ..services.categories import CategoryService
from ..services.parser import ParserService
from ..services.storage import StorageService


async def handle_manual_input(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    parser: ParserService = context.application.bot_data["parser"]
    categories_service: CategoryService = context.application.bot_data["categories"]
    bank_name = context.user_data.get("bank_name") or "Ручной банк"
    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    text = update.message.text if update.message else ""
    parsed = parser.parse(text, bank=bank_name, source="manual")
    categories = [BankCategory(name=item.category, rate=item.rate) for item in parsed.categories]
    merged = categories_service.merge_duplicates(categories)
    if not merged:
        await update.message.reply_text("Не удалось разобрать категории")
        return
    bank_id = await storage.save_bank(Bank(user_id=user_id, name=bank_name, categories=merged))
    await storage.log_ocr(user_id, bank_id, parsed.text, parsed.quality)
    await update.message.reply_text("Категории сохранены")
