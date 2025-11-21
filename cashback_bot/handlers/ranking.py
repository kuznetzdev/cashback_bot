from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..services.ranking import RankingService
from ..services.storage import StorageService


async def handle_ranking(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    ranking: RankingService = context.application.bot_data["ranking"]
    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    items = await storage.list_items(user_id)
    best_bank, total = ranking.best_overall_bank(items)
    best_sum_bank, best_sum = ranking.best_by_total_percent(items)
    gaps = ranking.highlight_gaps(items)
    suggestions = ranking.suggestions(items)
    lines = [
        f"Лучший банк по сумме %: {best_sum_bank} ({best_sum:.1f}%)",
        f"Самый выгодный банк: {best_bank} ({total:.1f}%)",
    ]
    if gaps:
        lines.append("Категории с большим разбросом: " + ", ".join(gaps))
    if suggestions:
        lines.extend(suggestions)
    await update.effective_message.reply_text("\n".join(lines))
