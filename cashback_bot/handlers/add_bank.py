from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..models.bank import Bank, BankCategory
from ..services.categories import CategoryService
from ..services.parser import ParserService
from ..services.storage import StorageService


async def handle_add_bank(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    parser: ParserService = context.application.bot_data["parser"]
    categories_service: CategoryService = context.application.bot_data["categories"]
    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    message = update.message
    if not message:
        return
    bank_name = message.text.strip()
    parsed = parser.parse("Супермаркеты 5%\nАЗС 5%", bank=bank_name, source="template")
    categories = [BankCategory(name=item.category, rate=item.rate) for item in parsed.categories]
    merged = categories_service.merge_duplicates(categories)
    bank = Bank(user_id=user_id, name=bank_name, categories=merged)
    bank_id = await storage.save_bank(bank)
    await message.reply_text(f"Банк {bank.name} сохранён (ID {bank_id}).")
