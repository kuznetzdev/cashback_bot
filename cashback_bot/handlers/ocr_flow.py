from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackContext

from ..models.bank import Bank, BankCategory
from ..services.categories import CategoryService
from ..services.image_safety import ImageSafetyService
from ..services.ocr import OCRService
from ..services.parser import ParserService
from ..services.queue import QueueTask, WorkflowQueue
from ..services.storage import StorageService

LOGGER = logging.getLogger(__name__)


async def handle_photo(update: Update, context: CallbackContext) -> None:
    storage: StorageService = context.application.bot_data["storage"]
    ocr: OCRService = context.application.bot_data["ocr"]
    parser: ParserService = context.application.bot_data["parser"]
    queue: WorkflowQueue = context.application.bot_data["queue"]
    categories_service: CategoryService = context.application.bot_data["categories"]
    safety: ImageSafetyService = context.application.bot_data["safety"]

    user_id = context.user_data.get("user_id")
    if user_id is None and update.effective_user:
        user_id = await storage.upsert_user(update.effective_user.id, context.application.bot_data["settings"].locale)
        context.user_data["user_id"] = user_id
    if not update.message or not update.message.photo:
        return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()
    report = safety.validate(bytes(image_bytes))
    if not report.ok:
        await update.message.reply_text("Фото не подходит для OCR")
        return
    bank_name = context.user_data.get("bank_name") or "OCR банк"
    task = QueueTask(user_id=user_id, bank_name=bank_name, image_bytes=bytes(image_bytes))
    if await queue.has_pending(user_id):
        await update.message.reply_text("Очередь занята, дождитесь завершения")
        return
    await queue.enqueue(task)
    await update.message.reply_text("Запускаю OCR…")
    async with queue.get_lock(user_id):
        next_task = await queue.next_task(user_id)
        if not next_task:
            return
        text = await ocr.read_text(next_task.image_bytes)
        if not text:
            await update.message.reply_text("Не удалось распознать текст")
            return
        parsed = parser.parse(text, bank=next_task.bank_name, source="ocr")
        categories = [BankCategory(name=item.category, rate=item.rate) for item in parsed.categories]
        merged = categories_service.merge_duplicates(categories)
        bank_id = await storage.save_bank(Bank(user_id=user_id, name=bank_name, categories=merged))
        await storage.log_ocr(user_id, bank_id, text, parsed.quality)
        await update.message.reply_text(categories_service.preview(merged))
