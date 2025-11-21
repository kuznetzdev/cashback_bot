from __future__ import annotations

import asyncio
import logging

from telegram.ext import (
    AIORateLimiter,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import load_settings
from .handlers.add_bank import handle_add_bank
from .handlers.bank_details import handle_bank_details
from .handlers.delete_flow import handle_delete
from .handlers.manual_input import handle_manual_input
from .handlers.menu import handle_menu
from .handlers.nlp_intents import handle_text_intents
from .handlers.ocr_flow import handle_photo
from .handlers.ranking import handle_ranking
from .handlers.settings import handle_settings, handle_settings_toggle
from .handlers.start import handle_start
from .i18n import Translator
from .services.aggregator import AggregatorService
from .services.categories import CategoryService
from .services.image_safety import ImageSafetyService
from .services.nlp import NLPService
from .services.ocr import OCRService
from .services.parser import ParserService
from .services.queue import WorkflowQueue
from .services.ranking import RankingService
from .services.scheduler import SchedulerService
from .services.storage import StorageService

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def build_application():
    settings = load_settings()
    storage = StorageService(settings.database_path)
    asyncio.get_event_loop().run_until_complete(storage.init_schema())
    translator = Translator(default_locale=settings.locale)
    ocr = OCRService(settings.temp_dir, workers=settings.ocr_workers)
    parser = ParserService()
    nlp = NLPService()
    queue = WorkflowQueue()
    categories = CategoryService()
    ranking = RankingService()
    aggregator = AggregatorService()
    scheduler = SchedulerService(settings.scheduler_timezone)
    safety = ImageSafetyService()

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    application.bot_data.update(
        {
            "settings": settings,
            "storage": storage,
            "translator": translator,
            "ocr": ocr,
            "parser": parser,
            "nlp": nlp,
            "queue": queue,
            "categories": categories,
            "ranking": ranking,
            "aggregator": aggregator,
            "scheduler": scheduler,
            "safety": safety,
        }
    )

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CallbackQueryHandler(handle_menu, pattern=r"^nav:main$"))
    application.add_handler(CallbackQueryHandler(handle_ranking, pattern=r"^nav:ranking$"))
    application.add_handler(CallbackQueryHandler(handle_settings, pattern=r"^nav:settings$"))
    application.add_handler(CallbackQueryHandler(handle_settings_toggle, pattern=r"^settings:"))
    application.add_handler(CallbackQueryHandler(handle_delete, pattern=r"^(bank|category):"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Regex(r"^банк "), handle_add_bank))
    application.add_handler(MessageHandler(filters.Regex(r"%"), handle_manual_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_intents))
    application.add_handler(CommandHandler("banks", handle_bank_details))

    return application


def main() -> None:
    application = build_application()
    LOGGER.info("Starting cashback bot")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
