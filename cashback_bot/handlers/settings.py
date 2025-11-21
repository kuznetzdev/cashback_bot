from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackContext

from ..keyboards.settings_menu import settings_menu
from ..models.user_settings import UserSettings
from ..services.storage import StorageService


async def handle_settings(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    query = update.callback_query
    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    if query:
        await query.answer()
    settings = await storage.load_settings(user_id)
    await update.effective_message.reply_text(str(settings), reply_markup=settings_menu())


async def handle_settings_toggle(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    toggle = parts[1]
    user_id = context.user_data.get("user_id")
    settings = await storage.load_settings(user_id)
    if toggle == "daily":
        settings.daily_notifications = not settings.daily_notifications
    elif toggle == "monthly":
        settings.monthly_notifications = not settings.monthly_notifications
    await storage.save_settings(settings)
    await query.edit_message_text(f"Настройки обновлены: daily={settings.daily_notifications}, monthly={settings.monthly_notifications}")
