"""Asynchronous Telegram bot entrypoint."""
from __future__ import annotations

import logging
from datetime import datetime

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import load_config
from .i18n import Translator
from .services.categories import CategoryNormalizer
from .services.db import AsyncDatabase, Receipt
from .services.nlp import NLPService, ParsedReceipt
from .services.ocr import OCRService
from .services.ranking import RankingService
from .services.scheduler import ReminderScheduler

LOGGER = logging.getLogger(__name__)

MENU_UPLOAD = "menu_upload"
MENU_MANUAL = "menu_manual"
MENU_ANALYTICS = "menu_analytics"
MENU_CABINET = "menu_cabinet"
MENU_SETTINGS = "menu_settings"
MENU_BACK = "menu_back"
SET_LANGUAGE_PREFIX = "set_lang_"

def build_menu(translator: Translator, locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(translator.translate("send_receipt_prompt", locale), callback_data=MENU_UPLOAD)],
            [InlineKeyboardButton(translator.translate("menu_manual", locale), callback_data=MENU_MANUAL)],
            [InlineKeyboardButton(translator.translate("menu_analytics", locale), callback_data=MENU_ANALYTICS)],
            [InlineKeyboardButton(translator.translate("menu_cabinet", locale), callback_data=MENU_CABINET)],
            [InlineKeyboardButton(translator.translate("menu_settings", locale), callback_data=MENU_SETTINGS)],
        ]
    )


async def ensure_user(
    context: ContextTypes.DEFAULT_TYPE, update_or_query: Update | CallbackQuery
) -> int:
    db: AsyncDatabase = context.application.bot_data["db"]
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale") or translator.default_locale
    if isinstance(update_or_query, Update):
        telegram_user = update_or_query.effective_user
    else:
        telegram_user = update_or_query.from_user
    if not telegram_user:
        raise RuntimeError("Cannot resolve user")
    user_id = await db.upsert_user(telegram_user.id, locale)
    context.user_data["user_id"] = user_id
    return user_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    config = context.application.bot_data["config"]
    context.user_data.setdefault("locale", config.locale)
    context.user_data["awaiting_photo"] = False
    context.user_data["expecting_manual"] = False
    await ensure_user(context, update)
    locale = context.user_data["locale"]
    keyboard = build_menu(translator, locale)
    await update.message.reply_text(
        translator.translate("start_message", locale),
        reply_markup=keyboard,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)

    if query.data == MENU_UPLOAD:
        await query.edit_message_text(translator.translate("send_receipt_prompt", locale))
        context.user_data["awaiting_photo"] = True
        context.user_data["expecting_manual"] = False
    elif query.data == MENU_MANUAL:
        await query.edit_message_text(translator.translate("manual_input_prompt", locale))
        context.user_data["expecting_manual"] = True
        context.user_data["awaiting_photo"] = False
    elif query.data == MENU_ANALYTICS:
        await show_analytics(query, context)
    elif query.data == MENU_CABINET:
        await show_cabinet(query, context)
    elif query.data == MENU_SETTINGS:
        await show_settings(query, context)
    elif query.data == MENU_BACK:
        keyboard = build_menu(translator, locale)
        context.user_data["awaiting_photo"] = False
        context.user_data["expecting_manual"] = False
        await query.edit_message_text(translator.translate("main_menu", locale), reply_markup=keyboard)


async def show_settings(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    current_locale = context.user_data.get("locale", translator.default_locale)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("English", callback_data=f"{SET_LANGUAGE_PREFIX}en")],
            [InlineKeyboardButton("Русский", callback_data=f"{SET_LANGUAGE_PREFIX}ru")],
            [InlineKeyboardButton(translator.translate("main_menu", current_locale), callback_data=MENU_BACK)],
        ]
    )
    await query.edit_message_text(
        translator.translate("menu_settings", current_locale), reply_markup=keyboard
    )


async def show_cabinet(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: AsyncDatabase = context.application.bot_data["db"]
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    user_id = context.user_data.get("user_id")
    if not user_id:
        user_id = await ensure_user(context, query)
    receipts = await db.fetch_recent_cashback(user_id)
    if not receipts:
        text = translator.translate("no_receipt", locale)
    else:
        header = translator.translate("recent_receipts", locale)
        lines = [f"<b>{header}</b>"]
        for receipt in receipts:
            lines.append(
                f"{receipt['purchase_date'] or '-'} — {receipt['merchant']} ({receipt['category']}): "
                f"{receipt['amount']} {receipt['currency']} cashback {receipt['cashback']}"
            )
        text = "\n".join(lines)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)


async def show_analytics(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: AsyncDatabase = context.application.bot_data["db"]
    config = context.application.bot_data["config"]
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    user_id = context.user_data.get("user_id")
    if not user_id:
        user_id = await ensure_user(context, query)
    ranking_service: RankingService = context.application.bot_data["ranking"]
    summaries = [summary async for summary in db.iter_category_totals(user_id, config.analytics_window_days)]
    ranking = ranking_service.build_category_ranking(summaries)
    if not ranking:
        text = translator.translate("no_receipt", locale)
    else:
        lines = [translator.translate("analytics_header", locale)]
        for idx, summary in enumerate(ranking, start=1):
            lines.append(
                translator.translate("analytics_row", locale).format(
                    idx=idx,
                    category=summary.category,
                    cashback=summary.total_cashback,
                    rate=summary.cashback_rate,
                )
            )
        text = "\n".join(lines)
    await query.edit_message_text(text)


async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    if not context.user_data.get("awaiting_photo"):
        await update.message.reply_text(translator.translate("photo_prompt", locale))
        return
    telegram_photo = update.message.photo[-1]
    image_file = await telegram_photo.get_file()
    image_bytes = await image_file.download_as_bytearray()
    ocr: OCRService = context.application.bot_data["ocr"]
    text = await ocr.read_text(bytes(image_bytes))
    if not text:
        await update.message.reply_text(translator.translate("ocr_failed", locale))
        return

    nlp: NLPService = context.application.bot_data["nlp"]
    parsed = nlp.parse_receipt(text)
    if not parsed:
        await update.message.reply_text(translator.translate("parse_failed", locale))
        return

    await persist_receipt(context, update, parsed)
    context.user_data["awaiting_photo"] = False


async def persist_receipt(
    context: ContextTypes.DEFAULT_TYPE, update: Update, parsed: ParsedReceipt
) -> None:
    db: AsyncDatabase = context.application.bot_data["db"]
    user_id = context.user_data.get("user_id")
    if not user_id:
        user_id = await ensure_user(context, update)
    receipt = Receipt(
        user_id=user_id,
        merchant=parsed.merchant,
        category=parsed.category,
        amount=parsed.amount,
        cashback=parsed.cashback,
        currency=parsed.currency,
        purchase_date=parsed.purchase_date or datetime.utcnow().strftime("%Y-%m-%d"),
    )
    await db.add_receipt(receipt)
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    await update.message.reply_text(translator.translate("receipt_added", locale))


async def process_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("expecting_manual"):
        return
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    parts = [part.strip() for part in update.message.text.split(";")]
    if len(parts) < 6:
        await update.message.reply_text(translator.translate("manual_format_error", locale))
        return

    merchant, category, amount, cashback, currency, purchase_date = parts[:6]
    nlp: NLPService = context.application.bot_data["nlp"]
    normalized_category = nlp.normalize_category(category)
    try:
        parsed = ParsedReceipt(
            merchant=merchant,
            category=normalized_category,
            amount=float(amount.replace(",", ".")),
            cashback=float(cashback.replace(",", ".")),
            currency=currency.upper(),
            purchase_date=purchase_date,
        )
    except ValueError:
        await update.message.reply_text(translator.translate("manual_amount_error", locale))
        return
    await persist_receipt(context, update, parsed)
    context.user_data["expecting_manual"] = False


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nlp: NLPService = context.application.bot_data["nlp"]
    intent = nlp.detect_intent(update.message.text)
    if intent == "delete_last":
        await delete_last_receipt(update, context)
    elif intent == "best_cashback":
        await show_best_cashback(update, context)
    elif context.user_data.get("expecting_manual"):
        await process_manual(update, context)
    else:
        translator: Translator = context.application.bot_data["translator"]
        locale = context.user_data.get("locale", translator.default_locale)
        await update.message.reply_text(translator.translate("unknown", locale))


async def delete_last_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: AsyncDatabase = context.application.bot_data["db"]
    user_id = context.user_data.get("user_id")
    if not user_id:
        user_id = await ensure_user(context, update)
    success = await db.delete_last_receipt(user_id)
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    if success:
        await update.message.reply_text(translator.translate("receipt_deleted", locale))
    else:
        await update.message.reply_text(translator.translate("no_receipt", locale))


async def show_best_cashback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: AsyncDatabase = context.application.bot_data["db"]
    config = context.application.bot_data["config"]
    ranking_service: RankingService = context.application.bot_data["ranking"]
    user_id = context.user_data.get("user_id")
    if not user_id:
        user_id = await ensure_user(context, update)
    summaries = [summary async for summary in db.iter_category_totals(user_id, config.analytics_window_days)]
    ranking = ranking_service.build_category_ranking(summaries, limit=1)
    translator: Translator = context.application.bot_data["translator"]
    locale = context.user_data.get("locale", translator.default_locale)
    if not ranking:
        await update.message.reply_text(translator.translate("no_cashback", locale))
        return
    top = ranking[0]
    await update.message.reply_text(
        translator.translate("best_cashback", locale).format(
            category=top.category, rate=top.cashback_rate
        )
    )


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    locale = query.data.replace(SET_LANGUAGE_PREFIX, "")
    context.user_data["locale"] = locale
    await ensure_user(context, query)
    translator: Translator = context.application.bot_data["translator"]
    keyboard = build_menu(translator, locale)
    await query.edit_message_text(translator.translate("main_menu", locale), reply_markup=keyboard)


async def reminder_callback(application: Application) -> None:
    translator: Translator = application.bot_data["translator"]
    db: AsyncDatabase = application.bot_data["db"]
    for row in await db.list_users():
        chat_id = row["telegram_id"]
        locale = row["language"]
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=translator.translate("reminder", locale),
            )
        except Exception:  # pylint: disable=broad-except
            LOGGER.exception("Failed to send reminder to %s", chat_id)


async def on_startup(application: Application) -> None:
    config = application.bot_data["config"]
    db: AsyncDatabase = application.bot_data["db"]
    await db.init()
    scheduler: ReminderScheduler = application.bot_data["scheduler"]

    async def callback() -> None:
        await reminder_callback(application)

    if application.bot_data["config"].enable_notifications:
        await scheduler.start(callback)


async def on_shutdown(application: Application) -> None:
    scheduler: ReminderScheduler = application.bot_data["scheduler"]
    await scheduler.stop()
    ocr: OCRService = application.bot_data["ocr"]
    await ocr.close()


def create_application() -> Application:
    config = load_config()
    translator = Translator(default_locale=config.locale)
    normalizer = CategoryNormalizer()
    nlp_service = NLPService(normalizer)
    db = AsyncDatabase(config.database_path)
    ocr_service = OCRService(config.ocr_temp_dir)
    ranking_service = RankingService()
    scheduler = ReminderScheduler(config.timezone)

    application = (
        ApplicationBuilder()
        .token(config.token)
        .rate_limiter(AIORateLimiter())
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    application.bot_data.update(
        {
            "config": config,
            "translator": translator,
            "nlp": nlp_service,
            "db": db,
            "ocr": ocr_service,
            "ranking": ranking_service,
            "scheduler": scheduler,
        }
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(change_language, pattern=f"^{SET_LANGUAGE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(handle_menu))

    application.add_handler(MessageHandler(filters.PHOTO, process_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return application


def main() -> None:
    application = create_application()
    LOGGER.info("Starting bot")
    application.run_polling()


if __name__ == "__main__":
    main()
