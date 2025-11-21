from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..services.nlp import NLPService
from ..services.ranking import RankingService
from ..services.storage import StorageService


async def handle_text_intents(update: Update, context: CallbackContext) -> None:
    nlp: NLPService = context.application.bot_data["nlp"]
    storage: StorageService = context.application.bot_data["storage"]
    ranking: RankingService = context.application.bot_data["ranking"]
    text = update.message.text if update.message else ""
    intent = nlp.build_intent(text)
    if not intent:
        return
    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    if intent.type == "delete_category":
        banks = await storage.list_banks(user_id)
        for bank in banks:
            for category in bank.categories:
                if category.name.lower() == intent.payload.get("category", "").lower():
                    category.deleted = True
            await storage.update_bank_categories(bank.id, bank.categories)
        await update.message.reply_text("Категория удалена")
    elif intent.type == "edit_percent":
        banks = await storage.list_banks(user_id)
        for bank in banks:
            for category in bank.categories:
                if category.name.lower() == intent.payload.get("category", "").lower():
                    category.rate = float(intent.payload["rate"])
            await storage.update_bank_categories(bank.id, bank.categories)
        await update.message.reply_text("Ставка обновлена")
    elif intent.type == "best_query":
        items = await storage.list_items(user_id)
        filtered = [it for it in items if it.normalized_category() == intent.payload.get("category", "").lower()]
        if not filtered:
            await update.message.reply_text("Нет данных по этой категории")
            return
        best_bank, _ = ranking.best_overall_bank(filtered)
        await update.message.reply_text(f"Лучший банк: {best_bank}")
    elif intent.type == "best_overview":
        items = await storage.list_items(user_id)
        best_bank, total = ranking.best_overall_bank(items)
        await update.message.reply_text(f"Ваш лучший банк: {best_bank} ({total:.1f}%)")
