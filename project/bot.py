"""Telegram bot orchestration logic built around the service layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, MutableMapping, Optional
from uuid import uuid4

from .i18n.translations import translate
from .services.categories import CategoryService
from .services.db import (
    Achievement,
    Bank,
    HistoryEntry,
    InMemoryDB,
    Recommendation,
    Template,
    Transaction,
)
from .services.extensions import ExtensionRegistry, default_recommendation_hook
from .services.nlp import NLPService
from .services.ocr import OCRService
from .services.ranking import RankingService
from .services.scheduler import SchedulerService
from .services.ui import (
    ACTION_PREFIX,
    DELETE_PREFIX,
    EDIT_PREFIX,
    NAV_PREFIX,
    Button,
    STATUS_MESSAGES,
    TYPING_INDICATORS,
    make_action_button,
    make_back_button,
    make_edit_button,
    make_delete_button,
    make_menu,
    make_nav_button,
    render_screen,
)


@dataclass
class Update:
    data: Dict[str, object]


@dataclass
class Context:
    data: Dict[str, object]


class CashbackBot:
    """Core bot responsible for handling commands and callbacks."""

    def __init__(
        self,
        db: Optional[InMemoryDB] = None,
        ocr: Optional[OCRService] = None,
        nlp: Optional[NLPService] = None,
        categories: Optional[CategoryService] = None,
        ranking: Optional[RankingService] = None,
        scheduler: Optional[SchedulerService] = None,
        extensions: Optional[ExtensionRegistry] = None,
    ) -> None:
        self.db = db or InMemoryDB()
        self.ocr = ocr or OCRService()
        self.nlp = nlp or NLPService()
        self.categories = categories or CategoryService()
        self.ranking = ranking or RankingService()
        self.scheduler = scheduler or SchedulerService()
        self.extensions = extensions or ExtensionRegistry()
        self.extensions.register_recommendation_hook(default_recommendation_hook)

    # Public API ---------------------------------------------------------

    def handle_start(self, user_id: int) -> Dict[str, object]:
        return self._render_home(user_id)

    def handle_callback(self, user_id: int, callback_data: str) -> Dict[str, object]:
        if callback_data.startswith(NAV_PREFIX):
            return self._handle_nav(user_id, callback_data[len(NAV_PREFIX) :])
        if callback_data.startswith(ACTION_PREFIX):
            return self._handle_action(user_id, callback_data[len(ACTION_PREFIX) :])
        if callback_data.startswith(EDIT_PREFIX):
            return self._handle_edit(user_id, callback_data[len(EDIT_PREFIX) :])
        if callback_data.startswith(DELETE_PREFIX):
            return self._handle_delete(user_id, callback_data[len(DELETE_PREFIX) :])
        raise ValueError(f"Unsupported callback data: {callback_data}")

    def handle_wizard_input(self, user_id: int, text: str) -> Dict[str, object]:
        state = self.db._profile(user_id).wizard_state  # type: ignore[attr-defined]
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        if state is None or state.step == 0:
            state = self.db.update_bank_wizard(user_id, name=text)
            keyboard = make_menu(
                [
                    [make_action_button("set_product_debit", "Дебетовая карта")],
                    [make_action_button("set_product_credit", "Кредитная карта")],
                ]
            )
            return render_screen(update, context, translate("wizard.bank.step_product"), keyboard)
        if state.step == 1:
            state = self.db.update_bank_wizard(user_id, product=text)
            keyboard = make_menu(
                [
                    [make_action_button("confirm_bank", "✅ Подтвердить")],
                    [make_back_button("home")],
                ]
            )
            return render_screen(update, context, translate("wizard.bank.step_confirm"), keyboard)
        return self._render_home(user_id)

    def process_receipt(self, user_id: int, image_payload: bytes) -> Dict[str, object]:
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {"typing": TYPING_INDICATORS["ocr"]}
        render_screen(update, context, STATUS_MESSAGES["processing"], make_menu([]))

        lines = self.ocr.extract_lines(image_payload)
        context["typing"] = TYPING_INDICATORS["nlp"]
        parsed_transactions = self.nlp.parse_lines(lines)

        transactions: List[Transaction] = []
        for parsed in parsed_transactions:
            category = self.categories.infer_category(parsed.description) or parsed.category
            transaction = Transaction(
                transaction_id=self._new_id("txn"),
                bank_id=self._default_bank(user_id).bank_id,
                amount=parsed.amount,
                category=category,
                description=parsed.description,
            )
            transactions.append(transaction)
            self.db.add_transaction(user_id, transaction)

        context["typing"] = TYPING_INDICATORS["db"]
        totals = self.ranking.summarize(self.db.list_transactions(user_id))
        achievements = self.ranking.build_achievements(totals)
        self.db.set_achievements(user_id, achievements)

        recommendations_texts = self.extensions.build_recommendations(
            self.db.list_transactions(user_id)
        )
        recommendations = [
            Recommendation(recommendation_id=self._new_id("rec"), text=text)
            for text in recommendations_texts
        ]
        self.db.set_recommendations(user_id, recommendations)

        self.db.add_history_entry(
            user_id,
            HistoryEntry(entry_id=self._new_id("history"), summary=f"Обработано {len(transactions)} покупок"),
        )

        text = self._format_analytics_text(totals, achievements)
        keyboard = self._home_keyboard()
        return render_screen(update, context, text, keyboard)

    # Internal helpers ---------------------------------------------------

    def _handle_nav(self, user_id: int, target: str) -> Dict[str, object]:
        if target == "home":
            return self._render_home(user_id)
        if target == "analytics":
            return self._render_analytics(user_id)
        if target == "recommendations":
            return self._render_recommendations(user_id)
        if target == "history":
            return self._render_history(user_id)
        if target == "gamification":
            return self._render_gamification(user_id)
        if target == "notifications":
            return self._render_notifications(user_id)
        if target == "templates":
            return self._render_templates(user_id)
        if target == "bank_wizard":
            self.db.start_bank_wizard(user_id)
            update: MutableMapping[str, object] = {}
            context: MutableMapping[str, object] = {}
            keyboard = make_menu([[make_back_button("home")]])
            return render_screen(
                update,
                context,
                translate("wizard.bank.step_name"),
                keyboard,
            )
        raise ValueError(f"Unknown navigation target: {target}")

    def _handle_action(self, user_id: int, action: str) -> Dict[str, object]:
        if action == "set_product_debit":
            self.db.update_bank_wizard(user_id, product="debit")
            keyboard = make_menu(
                [
                    [make_action_button("confirm_bank", "✅ Подтвердить")],
                    [make_back_button("home")],
                ]
            )
            update: MutableMapping[str, object] = {}
            context: MutableMapping[str, object] = {}
            return render_screen(update, context, translate("wizard.bank.step_confirm"), keyboard)
        if action == "set_product_credit":
            self.db.update_bank_wizard(user_id, product="credit")
            keyboard = make_menu(
                [
                    [make_action_button("confirm_bank", "✅ Подтвердить")],
                    [make_back_button("home")],
                ]
            )
            update: MutableMapping[str, object] = {}
            context: MutableMapping[str, object] = {}
            return render_screen(update, context, translate("wizard.bank.step_confirm"), keyboard)
        if action == "confirm_bank":
            bank = self.db.complete_bank_wizard(user_id, bank_id=self._new_id("bank"))
            self.db.add_history_entry(
                user_id,
                HistoryEntry(entry_id=self._new_id("history"), summary=f"Добавлен банк {bank.name}"),
            )
            return self._render_home(user_id)
        if action == "add_template":
            template = Template(
                template_id=self._new_id("tpl"),
                name="Кафе",
                fields={"category": "coffee"},
            )
            self.db.add_template(user_id, template)
            self.categories.register_template(template)
            return self._render_templates(user_id)
        if action == "enable_weekly_notifications":
            self._update_notifications(user_id, mode="weekly", hour=18)
            return self._render_notifications(user_id)
        if action == "enable_smart_notifications":
            self._update_notifications(user_id, mode="smart", hour=20)
            return self._render_notifications(user_id)
        raise ValueError(f"Unknown action: {action}")

    def _handle_edit(self, user_id: int, entity: str) -> Dict[str, object]:
        if entity.startswith("template_"):
            template_id = entity.split("_", 1)[1]
            template = Template(template_id=template_id, name="Обновлённый шаблон", fields={"category": "other"})
            self.db.add_template(user_id, template)
            self.categories.register_template(template)
            return self._render_templates(user_id)
        raise ValueError(f"Unsupported edit entity: {entity}")

    def _handle_delete(self, user_id: int, entity: str) -> Dict[str, object]:
        if entity.startswith("template_"):
            template_id = entity.split("_", 1)[1]
            self.db.delete_template(user_id, template_id)
            self.categories.unregister_template(template_id)
            return self._render_templates(user_id)
        raise ValueError(f"Unsupported delete entity: {entity}")

    # Screens -------------------------------------------------------------

    def _render_home(self, user_id: int) -> Dict[str, object]:
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        text = translate("menu.main")
        keyboard = self._home_keyboard()
        return render_screen(update, context, text, keyboard)

    def _home_keyboard(self) -> List[List[Button]]:
        return make_menu(
            [
                [make_nav_button("analytics", translate("menu.analytics"))],
                [make_nav_button("recommendations", translate("menu.recommendations"))],
                [make_nav_button("history", translate("menu.history"))],
                [make_nav_button("gamification", translate("menu.gamification"))],
                [make_nav_button("notifications", translate("menu.notifications"))],
                [make_nav_button("templates", translate("menu.templates"))],
                [make_nav_button("bank_wizard", translate("menu.bank_wizard"))],
            ]
        )

    def _render_analytics(self, user_id: int) -> Dict[str, object]:
        totals = self.ranking.summarize(self.db.list_transactions(user_id))
        if not totals:
            text = translate("analytics.empty")
        else:
            lines = ["📊 Сводка расходов"]
            lines.extend(f"• {category}: {amount:.2f} ₽" for category, amount in totals.items())
            text = "\n".join(lines)
        keyboard = make_menu([[make_back_button("home")]])
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        return render_screen(update, context, text, keyboard)

    def _render_recommendations(self, user_id: int) -> Dict[str, object]:
        recommendations = self.db.list_recommendations(user_id)
        if not recommendations:
            text = translate("recommendations.title") + "\n" + "Нет рекомендаций"
        else:
            lines = [translate("recommendations.title")]
            lines.extend(f"• {item.text}" for item in recommendations)
            text = "\n".join(lines)
        keyboard = make_menu([[make_back_button("home")]])
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        return render_screen(update, context, text, keyboard)

    def _render_history(self, user_id: int) -> Dict[str, object]:
        history = self.db.list_history(user_id)
        if not history:
            text = translate("history.empty")
        else:
            lines = ["История операций"]
            lines.extend(f"• {entry.summary}" for entry in history[-10:])
            text = "\n".join(lines)
        keyboard = make_menu([[make_back_button("home")]])
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        return render_screen(update, context, text, keyboard)

    def _render_gamification(self, user_id: int) -> Dict[str, object]:
        achievements = self.db.list_achievements(user_id)
        if not achievements:
            text = translate("gamification.level", level=1)
        else:
            lines = ["🏆 Достижения"]
            lines.extend(f"• {ach.title}: {ach.progress}%" for ach in achievements)
            text = "\n".join(lines)
        keyboard = make_menu([[make_back_button("home")]])
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        return render_screen(update, context, text, keyboard)

    def _render_notifications(self, user_id: int) -> Dict[str, object]:
        settings = self.db.get_notifications(user_id)
        text = translate("notifications.settings") + f"\nТекущий режим: {settings.mode} в {settings.hour}:00"
        keyboard = make_menu(
            [
                [make_action_button("enable_weekly_notifications", "Еженедельно в 18:00")],
                [make_action_button("enable_smart_notifications", "Умные уведомления")],
                [make_back_button("home")],
            ]
        )
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        return render_screen(update, context, text, keyboard)

    def _update_notifications(self, user_id: int, *, mode: str, hour: int) -> None:
        current = self.db.get_notifications(user_id)
        if current.mode != mode:
            self.scheduler.cancel(user_id, current.mode)
        settings = self.db.update_notifications(user_id, mode=mode, hour=hour)
        self.scheduler.schedule(user_id, settings.mode, settings.hour)

    def _render_templates(self, user_id: int) -> Dict[str, object]:
        templates = list(self.db._profile(user_id).templates.values())  # type: ignore[attr-defined]
        if not templates:
            lines = [translate("templates.empty")]
        else:
            lines = ["🧩 Шаблоны"]
            for template in templates:
                lines.append(f"• {template.name} → {template.fields}")
        keyboard_rows: List[List[Button]] = [
            [make_action_button("add_template", "➕ Добавить шаблон")]
        ]
        for template in templates:
            keyboard_rows.append(
                [
                    make_edit_button(f"template_{template.template_id}", "✏️ Редактировать"),
                    make_delete_button(f"template_{template.template_id}", "🗑 Удалить"),
                ]
            )
        keyboard_rows.append([make_back_button("home")])
        keyboard = make_menu(keyboard_rows)
        update: MutableMapping[str, object] = {}
        context: MutableMapping[str, object] = {}
        return render_screen(update, context, "\n".join(lines), keyboard)

    def _format_analytics_text(self, totals: Dict[str, float], achievements: List[Achievement]) -> str:
        if not totals:
            return translate("analytics.empty")
        lines = ["📊 Обновленная аналитика"]
        lines.extend(f"• {category}: {amount:.2f} ₽" for category, amount in totals.items())
        if achievements:
            lines.append("\n🏆 Новые достижения")
            lines.extend(f"• {ach.title}: {ach.progress}%" for ach in achievements)
        return "\n".join(lines)

    def _default_bank(self, user_id: int) -> Bank:
        profile = self.db._profile(user_id)  # type: ignore[attr-defined]
        if profile.banks:
            return next(iter(profile.banks.values()))
        bank = Bank(bank_id=self._new_id("bank"), name="Default Bank", product="debit")
        profile.banks[bank.bank_id] = bank
        return bank

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}"
