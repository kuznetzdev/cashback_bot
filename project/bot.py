"""Asynchronous Telegram bot entrypoint with advanced cashback analytics."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from telegram import CallbackQuery, Update
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

from .config import BotConfig, load_config
from .i18n import Translator
from .services.analytics import AnalyticsService
from .services.categories import CategoryNormalizer
from .services.db import AsyncDatabase
from .services.gamification import GamificationService
from .services.history import HistoryService
from .services.nlp import NLPService
from .services.notifications import NotificationService
from .services.ocr import OCRService
from .services.recommendations import RecommendationService
from .services.scheduler import ReminderScheduler
from .services.templates import TemplateService
from .services.ui import ButtonSpec, render_screen
from .services.wizard import WizardData, WizardService

LOGGER = logging.getLogger(__name__)

NAV_MAIN = "main"
NAV_WIZARD = "wizard"
NAV_ANALYTICS_PRO = "analytics_pro"
NAV_RECOMMENDATIONS = "recommendations"
NAV_HISTORY = "history"
NAV_PROFILE = "profile_extended"
NAV_SETTINGS = "settings"
NAV_TEMPLATES = "templates"

TOP_BANKS: Sequence[dict[str, Any]] = (
    {"name": "Tinkoff", "translations": {"ru": "Тинькофф"}},
    {"name": "Sberbank", "translations": {"ru": "Сбер"}},
    {"name": "Alfa-Bank", "translations": {"ru": "Альфа-Банк"}},
    {"name": "VTB", "translations": {"ru": "ВТБ"}},
    {"name": "Raiffeisen", "translations": {"ru": "Райффайзен"}},
    {"name": "Home Credit", "translations": {"ru": "Хоум Кредит"}},
    {"name": "Gazprombank", "translations": {"ru": "Газпромбанк"}},
    {"name": "Rosselkhozbank", "translations": {"ru": "Росельхозбанк"}},
    {"name": "Opening", "translations": {"ru": "Открытие"}},
    {"name": "Rosbank", "translations": {"ru": "Росбанк"}},
    {"name": "Ak Bars", "translations": {"ru": "Ак Барс"}},
    {"name": "UniCredit", "translations": {"ru": "ЮниКредит"}},
    {"name": "MTS Bank", "translations": {"ru": "МТС Банк"}},
    {"name": "Russian Standard", "translations": {"ru": "Русский Стандарт"}},
    {"name": "Sovcombank", "translations": {"ru": "Совкомбанк"}},
)


@dataclass
class CallbackCommand:
    kind: str
    parts: list[str]


async def ensure_user(context: ContextTypes.DEFAULT_TYPE, update_or_query: Update | CallbackQuery) -> int:
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


def parse_callback_data(data: str) -> CallbackCommand:
    parts = data.split(":")
    return CallbackCommand(kind=parts[0], parts=parts[1:])


def get_locale(context: ContextTypes.DEFAULT_TYPE) -> str:
    translator: Translator = context.application.bot_data["translator"]
    return context.user_data.get("locale", translator.default_locale)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: BotConfig = context.application.bot_data["config"]
    context.user_data.setdefault("locale", config.locale)
    await ensure_user(context, update)
    await show_main_screen(update, context, intro=True)


async def show_main_screen(
    source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE, *, intro: bool = False
) -> None:
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    keyboard = [
        [
            ButtonSpec(translator.translate("menu_wizard", locale), f"nav:{NAV_WIZARD}"),
        ],
        [
            ButtonSpec(translator.translate("menu_analytics_pro", locale), f"nav:{NAV_ANALYTICS_PRO}"),
        ],
        [
            ButtonSpec(translator.translate("menu_recommendations", locale), f"nav:{NAV_RECOMMENDATIONS}"),
        ],
        [
            ButtonSpec(translator.translate("menu_history", locale), f"nav:{NAV_HISTORY}"),
        ],
        [
            ButtonSpec(translator.translate("menu_profile", locale), f"nav:{NAV_PROFILE}"),
        ],
        [
            ButtonSpec(translator.translate("menu_settings", locale), f"nav:{NAV_SETTINGS}"),
        ],
    ]
    text = translator.translate("screen_main", locale)
    if intro:
        text = f"{translator.translate('start_message', locale)}\n\n{text}"
    await render_screen(source, context, text, keyboard=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    command = parse_callback_data(query.data or "")
    if command.kind == "nav":
        await handle_navigation(query, context, command.parts)
    elif command.kind == "action":
        await handle_action(query, context, command.parts)
    elif command.kind == "edit":
        await handle_edit(query, context, command.parts)
    elif command.kind == "del":
        await handle_delete(query, context, command.parts)


async def handle_navigation(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if not parts:
        return
    screen = parts[0]
    if screen == NAV_MAIN:
        await show_main_screen(query, context)
    elif screen == NAV_WIZARD:
        step = parts[1] if len(parts) > 1 else None
        await show_wizard(query, context, step)
    elif screen == NAV_ANALYTICS_PRO:
        await show_analytics_pro(query, context)
    elif screen == NAV_RECOMMENDATIONS:
        await show_recommendations(query, context)
    elif screen == NAV_HISTORY:
        await show_history_screen(query, context)
    elif screen == NAV_PROFILE:
        await show_profile_screen(query, context)
    elif screen == NAV_SETTINGS:
        await show_settings_screen(query, context)
    elif screen == NAV_TEMPLATES:
        context.user_data["templates_for_wizard"] = len(parts) > 1 and parts[1] == "wizard"
        await show_templates_screen(query, context)


async def handle_action(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if not parts:
        return
    action = parts[0]
    if action == "wizard_bank":
        await handle_wizard_bank_selection(query, context, parts)
    elif action == "wizard_other":
        await handle_wizard_other(query, context)
    elif action == "wizard_input":
        await handle_wizard_input(query, context, parts)
    elif action == "wizard_confirm":
        await handle_wizard_confirm(query, context)
    elif action == "wizard_edit":
        await handle_wizard_edit(query, context)
    elif action == "wizard_cancel":
        await handle_wizard_cancel(query, context)
    elif action == "history_clear":
        await clear_history(query, context)
    elif action == "notifications_toggle":
        await toggle_notification(query, context, parts)
    elif action == "template_new":
        await prompt_new_template(query, context)
    elif action == "template_use":
        await handle_template_use(query, context, parts)


async def handle_edit(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if len(parts) < 2:
        return
    element, identifier = parts[0], parts[1]
    if element == "template":
        await prompt_edit_template(query, context, int(identifier))


async def handle_delete(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if len(parts) < 2:
        return
    target, identifier = parts[0], parts[1]
    if target == "template":
        await delete_template(query, context, int(identifier))


async def show_wizard(
    source: Update | CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    step_override: str | None = None,
) -> None:
    translator: Translator = context.application.bot_data["translator"]
    wizard: WizardService = context.application.bot_data["wizard"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    data = await wizard.load(user_id)
    if step_override:
        data.step = step_override
        await wizard.update(data)
    step = data.step
    if step == "select_bank":
        keyboard_rows: list[list[ButtonSpec]] = []
        for bank in context.application.bot_data["top_bank_index"]:
            label = bank["translations"].get(locale, bank["name"])
            keyboard_rows.append([ButtonSpec(label, f"action:wizard_bank:{bank['id']}")])
        keyboard_rows.append([
            ButtonSpec(translator.translate("wizard_other", locale), "action:wizard_other"),
        ])
        keyboard_rows.append([
            ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel"),
        ])
        await render_screen(
            source,
            context,
            translator.translate("wizard_select_bank", locale),
            keyboard=keyboard_rows,
        )
    elif step == "custom_name":
        context.user_data["wizard_expect"] = "bank_name"
        await render_screen(
            source,
            context,
            translator.translate("wizard_enter_name", locale),
            keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:select_bank")]],
        )
    elif step == "input_mode":
        keyboard = [
            [ButtonSpec(translator.translate("wizard_input_photo", locale), "action:wizard_input:photo")],
            [ButtonSpec(translator.translate("wizard_input_text", locale), "action:wizard_input:text")],
            [ButtonSpec(translator.translate("wizard_input_template", locale), f"nav:{NAV_TEMPLATES}:wizard")],
            [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:select_bank")],
            [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
        ]
        await render_screen(
            source,
            context,
            translator.translate("wizard_choose_input", locale),
            keyboard=keyboard,
        )
    elif step in {"input_photo", "input_text"}:
        key = "wizard_expect_photo" if step == "input_photo" else "wizard_expect_text"
        keyboard = [
            [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:input_mode")],
            [ButtonSpec(translator.translate("button_skip", locale), f"nav:{NAV_WIZARD}:preview")],
            [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
        ]
        await render_screen(
            source,
            context,
            translator.translate(key, locale),
            keyboard=keyboard,
        )
    elif step == "preview":
        text = build_wizard_preview(data, translator, locale)
        keyboard = [
            [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:input_mode")],
            [ButtonSpec(translator.translate("button_edit", locale), "action:wizard_edit")],
            [ButtonSpec(translator.translate("button_confirm", locale), "action:wizard_confirm")],
            [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
        ]
        await render_screen(source, context, text, keyboard=keyboard)


def build_wizard_preview(data: WizardData, translator: Translator, locale: str) -> str:
    lines = [translator.translate("wizard_preview", locale)]
    if data.bank_name:
        lines.append(f"<b>{data.bank_name}</b>")
    if not data.categories:
        lines.append(translator.translate("wizard_no_categories", locale))
        return "\n".join(lines)
    for entry in data.categories:
        rate = float(entry.get("rate", 0.0)) * 100
        level = int(entry.get("level", 1))
        lines.append(f"• L{level} {entry.get('name')}: {rate:.2f}%")
    return "\n".join(lines)


async def handle_wizard_bank_selection(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if len(parts) < 2:
        return
    bank_id = int(parts[1])
    wizard: WizardService = context.application.bot_data["wizard"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    data = await wizard.load(user_id)
    for bank in context.application.bot_data["top_bank_index"]:
        if bank["id"] == bank_id:
            data.bank_id = bank_id
            data.bank_name = bank["translations"].get(locale, bank["name"])
            break
    data.step = "input_mode"
    await wizard.update(data)
    await render_screen(
        query,
        context,
        translator.translate("wizard_choose_input", locale),
        keyboard=[
            [ButtonSpec(translator.translate("wizard_input_photo", locale), "action:wizard_input:photo")],
            [ButtonSpec(translator.translate("wizard_input_text", locale), "action:wizard_input:text")],
            [ButtonSpec(translator.translate("wizard_input_template", locale), f"nav:{NAV_TEMPLATES}:wizard")],
            [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
        ],
    )


async def handle_wizard_other(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    wizard: WizardService = context.application.bot_data["wizard"]
    user_id = await ensure_user(context, query)
    data = await wizard.load(user_id)
    data.bank_id = None
    data.bank_name = None
    data.step = "custom_name"
    await wizard.update(data)
    await show_wizard(query, context, "custom_name")


async def handle_wizard_input(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if len(parts) < 2:
        return
    mode = parts[1]
    wizard: WizardService = context.application.bot_data["wizard"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    data = await wizard.load(user_id)
    data.input_mode = mode
    if mode == "photo":
        data.step = "input_photo"
        context.user_data["wizard_expect"] = "photo"
        await wizard.update(data)
        await render_screen(
            query,
            context,
            translator.translate("wizard_expect_photo", locale),
            keyboard=[
                [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:input_mode")],
                [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
            ],
        )
    elif mode == "text":
        data.step = "input_text"
        context.user_data["wizard_expect"] = "text"
        await wizard.update(data)
        await render_screen(
            query,
            context,
            translator.translate("wizard_expect_text", locale),
            keyboard=[
                [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:input_mode")],
                [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
            ],
        )


async def handle_wizard_edit(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    wizard: WizardService = context.application.bot_data["wizard"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    data = await wizard.load(user_id)
    data.step = "input_text"
    await wizard.update(data)
    context.user_data["wizard_expect"] = "text"
    await render_screen(
        query,
        context,
        translator.translate("wizard_expect_text", locale),
        keyboard=[
            [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:preview")],
            [ButtonSpec(translator.translate("button_cancel", locale), "action:wizard_cancel")],
        ],
    )


async def handle_wizard_confirm(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    wizard: WizardService = context.application.bot_data["wizard"]
    history: HistoryService = context.application.bot_data["history"]
    gamification: GamificationService = context.application.bot_data["gamification"]
    db: AsyncDatabase = context.application.bot_data["db"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    data = await wizard.load(user_id)
    try:
        bank_id = await wizard.finalize(data)
    except ValueError as error:
        await render_screen(
            query,
            context,
            str(error),
            keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}:preview")]],
        )
        return
    await db.update_last_activity(user_id, bank_update=True)
    await history.record(user_id, "bank_added", {"bank_id": bank_id, "name": data.bank_name})
    await gamification.award(user_id, "add_bank")
    await render_screen(
        query,
        context,
        translator.translate("wizard_confirm", locale),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")]],
    )


async def handle_wizard_cancel(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    wizard: WizardService = context.application.bot_data["wizard"]
    user_id = await ensure_user(context, query)
    await wizard.cancel(user_id)
    context.user_data.pop("wizard_expect", None)
    await show_main_screen(query, context)


async def handle_template_use(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if len(parts) < 2:
        return
    identifier = ":".join(parts[1:])
    template_service: TemplateService = context.application.bot_data["templates"]
    wizard: WizardService = context.application.bot_data["wizard"]
    user_id = await ensure_user(context, query)
    locale = get_locale(context)
    views = await template_service.list_templates(user_id, locale)
    selected = next((view for view in views if view.identifier == identifier), None)
    translator: Translator = context.application.bot_data["translator"]
    if selected is None:
        await render_screen(
            query,
            context,
            translator.translate("templates_invalid", locale),
            keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_TEMPLATES}:wizard")]],
        )
        return
    data = await wizard.load(user_id)
    data.categories = wizard.apply_template(selected.payload)
    data.step = "preview"
    await wizard.update(data)
    context.user_data.pop("templates_for_wizard", None)
    await show_wizard(query, context, "preview")


async def show_analytics_pro(source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    analytics: AnalyticsService = context.application.bot_data["analytics"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    worst = await analytics.top_worst_categories(user_id)
    buckets = await analytics.top_by_buckets(user_id)
    strengths = await analytics.bank_strength_score(user_id)
    coverage = await analytics.category_coverage_summary(user_id)
    lines = [f"<b>{translator.translate('analytics_pro_header', locale)}</b>"]
    has_data = False
    if worst:
        has_data = True
        lines.append(translator.translate("analytics_worst_header", locale))
        for insight in worst:
            lines.append(f"• {insight.bank_name}: {insight.category} — {insight.rate * 100:.2f}%")
    if buckets:
        has_data = True
        lines.append("")
        lines.append(translator.translate("analytics_bucket_header", locale))
        for bucket, items in buckets.items():
            lines.append(f"{bucket}:")
            for insight in items[:5]:
                lines.append(f"  • {insight.bank_name} — {insight.category} ({insight.rate * 100:.2f}%)")
    if strengths:
        has_data = True
        lines.append("")
        lines.append(translator.translate("analytics_strength_header", locale))
        for strength in strengths:
            lines.append(
                f"• {strength.bank_name}: {strength.score} (top={strength.top_categories}, weak={strength.weak_categories})"
            )
    if coverage:
        has_data = True
        lines.append("")
        lines.append(translator.translate("analytics_coverage_header", locale))
        for item in coverage:
            lines.append(
                translator.translate("analytics_coverage_line", locale).format(
                    category=item.category,
                    best_bank=item.best_bank,
                    best_rate=item.best_rate * 100,
                    bank_count=item.bank_count,
                    average_rate=item.average_rate * 100,
                )
            )
    if not has_data:
        lines.append(translator.translate("analytics_no_data", locale))
    await render_screen(
        source,
        context,
        "\n".join(lines),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")]],
    )

async def show_recommendations(source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    recommendations_service: RecommendationService = context.application.bot_data["recommendations"]
    db: AsyncDatabase = context.application.bot_data["db"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    rows = await db.fetch_all_category_rates(user_id)
    lines = [f"<b>{translator.translate('recommendations_header', locale)}</b>"]
    if not rows:
        lines.append(translator.translate("no_cashback", locale))
    else:
        top_category = rows[0]["normalized_name"]
        best = await recommendations_service.recommend_best_card_for(user_id, top_category)
        if best:
            lines.append(
                translator.translate("recommendation_best_card", locale).format(
                    category=best.context["category"],
                    bank=best.details,
                    rate=best.context["rate"],
                )
            )
        move = await recommendations_service.recommend_where_to_move_cashback(user_id)
        if move:
            lines.append(
                translator.translate("recommendation_move", locale).format(
                    bank=move.details,
                    category=move.context["category"],
                    rate=move.context["rate"],
                )
            )
        seen_banks: set[int] = set()
        for row in rows:
            if row["user_bank_id"] in seen_banks:
                continue
            seen_banks.add(row["user_bank_id"])
            updates = await recommendations_service.recommend_what_to_update(
                user_id, int(row["user_bank_id"])
            )
            if updates:
                first = updates[0]
                lines.append(
                    translator.translate("recommendation_update", locale).format(
                        category=first.details,
                        rate=first.context["rate"],
                    )
                )
        opportunities = await recommendations_service.recommend_new_category_opportunities(user_id)
        for item in opportunities[:3]:
            lines.append(
                translator.translate("recommendation_opportunity", locale).format(
                    category=item.details,
                    rate=item.context["rate"],
                )
            )
    await render_screen(
        source,
        context,
        "\n".join(lines),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")]],
    )


async def show_history_screen(source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    history: HistoryService = context.application.bot_data["history"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    entries = await history.list(user_id)
    lines = [f"<b>{translator.translate('history_header', locale)}</b>"]
    if not entries:
        lines.append(translator.translate("history_empty", locale))
    else:
        for entry in entries:
            lines.append(f"• {entry['created_at']}: {entry['action']}")
    keyboard = [
        [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")],
        [ButtonSpec(translator.translate("button_delete", locale), "action:history_clear")],
    ]
    await render_screen(source, context, "\n".join(lines), keyboard=keyboard)


async def clear_history(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    history: HistoryService = context.application.bot_data["history"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    await history.clear(user_id)
    await render_screen(
        query,
        context,
        translator.translate("history_cleared", locale),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_HISTORY}")]],
    )


async def show_profile_screen(source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    gamification: GamificationService = context.application.bot_data["gamification"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    profile = await gamification.profile(user_id)
    text = "\n".join(
        [
            f"<b>{translator.translate('profile_header', locale)}</b>",
            translator.translate("profile_points", locale).format(points=profile.points),
            translator.translate("profile_level", locale).format(level=profile.level),
        ]
    )
    await render_screen(
        source,
        context,
        text,
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")]],
    )


async def show_settings_screen(source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    notification_service: NotificationService = context.application.bot_data["notifications"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    text = await notification_service.render_settings(user_id, locale)
    keyboard = [
        [ButtonSpec(translator.translate("notifications_monthly", locale), "action:notifications_toggle:monthly")],
        [ButtonSpec(translator.translate("notifications_warning", locale), "action:notifications_toggle:warning")],
        [ButtonSpec(translator.translate("notifications_critical", locale), "action:notifications_toggle:critical")],
        [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")],
    ]
    await render_screen(source, context, text, keyboard=keyboard)


async def toggle_notification(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, parts: Sequence[str]
) -> None:
    if len(parts) < 2:
        return
    notification_service: NotificationService = context.application.bot_data["notifications"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    settings = await notification_service.get_settings(user_id)
    toggle = parts[1]
    monthly = settings.monthly_enabled
    warning = settings.inactivity_warning_enabled
    critical = settings.inactivity_critical_enabled
    if toggle == "monthly":
        monthly = not monthly
    elif toggle == "warning":
        warning = not warning
    elif toggle == "critical":
        critical = not critical
    await notification_service.update_settings(
        user_id,
        monthly=monthly,
        warning=warning,
        critical=critical,
    )
    await render_screen(
        query,
        context,
        await notification_service.render_settings(user_id, locale),
        keyboard=[
            [ButtonSpec(translator.translate("notifications_monthly", locale), "action:notifications_toggle:monthly")],
            [ButtonSpec(translator.translate("notifications_warning", locale), "action:notifications_toggle:warning")],
            [ButtonSpec(translator.translate("notifications_critical", locale), "action:notifications_toggle:critical")],
            [ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_MAIN}")],
        ],
    )


async def show_templates_screen(source: Update | CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    template_service: TemplateService = context.application.bot_data["templates"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, source)
    for_wizard = context.user_data.get("templates_for_wizard", False)
    views = await template_service.list_templates(user_id, locale)
    lines = [f"<b>{translator.translate('templates_header', locale)}</b>"]
    keyboard: list[list[ButtonSpec]] = []
    if not views:
        lines.append(translator.translate("templates_empty", locale))
    for view in views:
        lines.append(f"• {view.title}")
        if for_wizard:
            keyboard.append([ButtonSpec(view.title, f"action:template_use:{view.identifier}")])
        elif not view.is_default:
            template_id = view.identifier.split(":", 1)[1]
            keyboard.append([
                ButtonSpec(translator.translate("button_edit", locale), f"edit:template:{template_id}"),
                ButtonSpec(translator.translate("button_delete", locale), f"del:template:{template_id}"),
            ])
    if not for_wizard:
        keyboard.append([ButtonSpec(translator.translate("templates_add", locale), "action:template_new")])
    keyboard.append([ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_WIZARD}" if for_wizard else f"nav:{NAV_MAIN}")])
    await render_screen(source, context, "\n".join(lines), keyboard=keyboard)


async def prompt_new_template(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    context.user_data["awaiting_template"] = {"mode": "create"}
    await render_screen(
        query,
        context,
        translator.translate("templates_prompt_new", locale),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_TEMPLATES}")]],
    )


async def prompt_edit_template(
    query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, template_id: int
) -> None:
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    context.user_data["awaiting_template"] = {"mode": "edit", "id": template_id}
    await render_screen(
        query,
        context,
        translator.translate("templates_prompt_new", locale),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_TEMPLATES}")]],
    )


async def delete_template(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> None:
    template_service: TemplateService = context.application.bot_data["templates"]
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    user_id = await ensure_user(context, query)
    await template_service.delete_template(user_id, template_id)
    await render_screen(
        query,
        context,
        translator.translate("templates_deleted", locale),
        keyboard=[[ButtonSpec(translator.translate("button_back", locale), f"nav:{NAV_TEMPLATES}")]],
    )


def parse_template_input(text: str) -> tuple[str, list[str]] | None:
    if "|" not in text:
        return None
    name, fields = text.split("|", 1)
    categories = [field.strip() for field in fields.split(",") if field.strip()]
    if not name.strip() or not categories:
        return None
    return name.strip(), categories


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    expect = context.user_data.get("wizard_expect")
    if expect != "photo":
        await update.message.reply_text(translator.translate("status_processing", locale))
        return
    wizard: WizardService = context.application.bot_data["wizard"]
    ocr: OCRService = context.application.bot_data["ocr"]
    user_id = await ensure_user(context, update)
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()
    await render_screen(update, context, translator.translate("status_ocr", locale))
    text = await ocr.read_text(bytes(image_bytes))
    if not text:
        await update.message.reply_text(translator.translate("ocr_failed", locale))
        return
    categories = wizard.parse_categories_text(text)
    data = await wizard.load(user_id)
    data.categories = categories
    data.step = "preview"
    await wizard.update(data)
    context.user_data.pop("wizard_expect", None)
    await show_wizard(update, context, "preview")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    translator: Translator = context.application.bot_data["translator"]
    locale = get_locale(context)
    text = update.message.text
    awaiting = context.user_data.get("wizard_expect")
    if awaiting == "bank_name":
        wizard: WizardService = context.application.bot_data["wizard"]
        user_id = await ensure_user(context, update)
        data = await wizard.load(user_id)
        data.bank_name = text.strip()
        data.step = "input_mode"
        await wizard.update(data)
        context.user_data.pop("wizard_expect", None)
        await show_wizard(update, context, "input_mode")
        return
    if awaiting == "text":
        wizard: WizardService = context.application.bot_data["wizard"]
        user_id = await ensure_user(context, update)
        categories = wizard.parse_categories_text(text)
        if not categories:
            await update.message.reply_text(translator.translate("manual_format_error", locale))
            return
        data = await wizard.load(user_id)
        data.categories = categories
        data.step = "preview"
        await wizard.update(data)
        context.user_data.pop("wizard_expect", None)
        await show_wizard(update, context, "preview")
        return
    template_context = context.user_data.get("awaiting_template")
    if template_context:
        parsed = parse_template_input(text)
        if not parsed:
            await update.message.reply_text(translator.translate("templates_invalid", locale))
            return
        name, fields = parsed
        template_service: TemplateService = context.application.bot_data["templates"]
        user_id = await ensure_user(context, update)
        payload = {"fields": fields}
        if template_context["mode"] == "edit":
            await template_service.upsert_template(user_id, "custom", name, payload, template_context["id"])
        else:
            await template_service.upsert_template(user_id, "custom", name, payload)
        context.user_data.pop("awaiting_template", None)
        await update.message.reply_text(translator.translate("templates_saved", locale))
        await show_templates_screen(update, context)
        return
    nlp: NLPService = context.application.bot_data["nlp"]
    intent = nlp.detect_intent(text)
    if intent == "recommendations":
        await show_recommendations(update, context)
    elif intent == "history":
        await show_history_screen(update, context)
    elif intent == "profile":
        await show_profile_screen(update, context)
    else:
        await update.message.reply_text(translator.translate("unknown", locale))


async def reminder_callback(application: Application) -> None:
    notification_service: NotificationService = application.bot_data["notifications"]
    await notification_service.process_notifications(application)


async def on_startup(application: Application) -> None:
    config: BotConfig = application.bot_data["config"]
    db: AsyncDatabase = application.bot_data["db"]
    await db.init()
    top_bank_index = []
    for bank in TOP_BANKS:
        bank_id = await db.ensure_bank(bank["name"], bank.get("translations"))
        entry = {"id": bank_id, "name": bank["name"], "translations": bank.get("translations", {})}
        top_bank_index.append(entry)
    application.bot_data["top_bank_index"] = top_bank_index
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
    ocr_service = OCRService(config.ocr_temp_dir, primary_lang=config.ocr_primary_lang, secondary_lang=config.ocr_secondary_lang)
    scheduler = ReminderScheduler(config.timezone)
    template_service = TemplateService(db)
    wizard_service = WizardService(db, normalizer)
    analytics_service = AnalyticsService(db, normalizer)
    recommendation_service = RecommendationService(db, normalizer)
    history_service = HistoryService(db, config.max_history_records)
    gamification_service = GamificationService(db)
    notification_service = NotificationService(db, translator, config)

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
            "scheduler": scheduler,
            "templates": template_service,
            "wizard": wizard_service,
            "analytics": analytics_service,
            "recommendations": recommendation_service,
            "history": history_service,
            "gamification": gamification_service,
            "notifications": notification_service,
        }
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return application


def main() -> None:
    application = create_application()
    LOGGER.info("Starting bot")
    application.run_polling()


if __name__ == "__main__":
    main()
