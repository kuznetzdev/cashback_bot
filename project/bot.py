"""Telegram bot orchestration logic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, MutableMapping, Optional

from project.i18n.translations import DEFAULT_LOCALE, translate
from project.services import ui
from project.services.categories import CategoryService
from project.services.db import Bank, Database, Template, Transaction
from project.services.extensions import GamificationEngine, RecommendationEngine
from project.services.nlp import NlpService
from project.services.ocr import OcrService
from project.services.ranking import RankingService
from project.services.scheduler import SchedulerService


@dataclass
class Update:
    """Simplified update structure used in tests."""

    chat_id: int
    message_text: Optional[str] = None
    callback_data: Optional[str] = None


class CashbackBot:
    """Coordinates UI and services according to user input."""

    WIZARD_STEPS = ("name", "account", "preferences")

    def __init__(
        self,
        db: Database,
        ocr: OcrService,
        nlp: NlpService,
        categories: CategoryService,
        ranking: RankingService,
        scheduler: SchedulerService,
        recommendation_engine: RecommendationEngine,
        gamification_engine: GamificationEngine,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        self.db = db
        self.ocr = ocr
        self.nlp = nlp
        self.categories = categories
        self.ranking = ranking
        self.scheduler = scheduler
        self.recommendation_engine = recommendation_engine
        self.gamification_engine = gamification_engine
        self.locale = locale
        self._id_counter = 0

    # ------------------------------------------------------------------ helpers -----
    def _next_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}-{self._id_counter}"

    def _chat_state(self, context: MutableMapping[str, object], chat_id: int) -> Dict[str, object]:
        chats: Dict[int, Dict[str, object]] = context.setdefault("chat_state", {})  # type: ignore[assignment]
        return chats.setdefault(chat_id, {})

    def _push_indicator(self, context: MutableMapping[str, object], chat_id: int, indicator: str) -> None:
        indicators: List[Dict[str, object]] = context.setdefault("indicators", [])  # type: ignore[assignment]
        indicators.append({"chat_id": chat_id, "type": indicator})

    def _render_main_menu(self, update: Update, context: MutableMapping[str, object]) -> None:
        buttons = [
            ui.KeyboardButton(translate("main_menu.add_bank", self.locale), ui.nav_callback("add_bank")),
            ui.KeyboardButton(translate("main_menu.manual_templates", self.locale), ui.nav_callback("manual_templates")),
            ui.KeyboardButton(translate("main_menu.pro_analytics", self.locale), ui.nav_callback("pro_analytics")),
            ui.KeyboardButton(translate("main_menu.recommendations", self.locale), ui.nav_callback("recommendations")),
            ui.KeyboardButton(translate("main_menu.history", self.locale), ui.nav_callback("history")),
            ui.KeyboardButton(translate("main_menu.gamification", self.locale), ui.nav_callback("gamification")),
            ui.KeyboardButton(translate("main_menu.notifications", self.locale), ui.nav_callback("notifications")),
        ]
        keyboard = ui.single_column(buttons)
        ui.render_screen(update.__dict__, context, translate("main_menu.title", self.locale), keyboard)

    def start(self, update: Update, context: MutableMapping[str, object]) -> None:
        self._render_main_menu(update, context)

    # --------------------------------------------------------------- callback flow --
    def handle_callback(self, update: Update, context: MutableMapping[str, object]) -> None:
        data = update.callback_data or ""
        if data.startswith(ui.CALLBACK_NAV_PREFIX):
            self._handle_navigation(update, context, data[len(ui.CALLBACK_NAV_PREFIX):])
        elif data.startswith(ui.CALLBACK_ACTION_PREFIX):
            self._handle_action(update, context, data[len(ui.CALLBACK_ACTION_PREFIX):])
        elif data.startswith(ui.CALLBACK_EDIT_PREFIX):
            self._start_template_edit(update, context, data[len(ui.CALLBACK_EDIT_PREFIX):])
        elif data.startswith(ui.CALLBACK_DELETE_PREFIX):
            self._delete_template(update, context, data[len(ui.CALLBACK_DELETE_PREFIX):])
        else:
            ui.render_screen(update.__dict__, context, translate("status.error", self.locale), None)

    def handle_message(self, update: Update, context: MutableMapping[str, object]) -> None:
        chat_state = self._chat_state(context, update.chat_id)
        wizard_state = chat_state.get("bank_wizard")
        template_state = chat_state.get("template_edit")

        if wizard_state:
            self._continue_bank_wizard(update, context, wizard_state)
            return
        if template_state:
            self._finalise_template_edit(update, context, template_state)
            return
        if chat_state.get("awaiting_manual_template"):
            self._save_manual_template(update, context, update.message_text or "")
            chat_state.pop("awaiting_manual_template", None)
            return
        ui.render_screen(update.__dict__, context, translate("status.error", self.locale), None)

    # --------------------------------------------------------------- navigation -----
    def _handle_navigation(self, update: Update, context: MutableMapping[str, object], target: str) -> None:
        if target == "add_bank":
            self._start_bank_wizard(update, context)
        elif target == "manual_templates":
            self._render_templates(update, context)
        elif target == "pro_analytics":
            self._show_pro_analytics(update, context)
        elif target == "recommendations":
            self._show_recommendations(update, context)
        elif target == "history":
            self._show_history(update, context)
        elif target == "gamification":
            self._show_gamification(update, context)
        elif target == "notifications":
            self._show_notifications(update, context)
        else:
            self._render_main_menu(update, context)

    def _handle_action(self, update: Update, context: MutableMapping[str, object], action: str) -> None:
        chat_state = self._chat_state(context, update.chat_id)
        if action == "templates:add":
            chat_state["awaiting_manual_template"] = True
            ui.render_screen(update.__dict__, context, translate("templates.manual_prompt", self.locale), None)
        elif action.startswith("notifications:"):
            mode = action.split(":", 1)[1]
            self._update_notifications(update, context, mode)
        elif action == "process:receipt":
            self._process_receipt(update, context)
        else:
            ui.render_screen(update.__dict__, context, translate("status.error", self.locale), None)

    # --------------------------------------------------------------- bank wizard ----
    def _start_bank_wizard(self, update: Update, context: MutableMapping[str, object]) -> None:
        chat_state = self._chat_state(context, update.chat_id)
        chat_state["bank_wizard"] = {"step": 0, "data": {}}
        self._prompt_bank_wizard(update, context)

    def _continue_bank_wizard(self, update: Update, context: MutableMapping[str, object], wizard_state: Dict[str, object]) -> None:
        text = (update.message_text or "").strip()
        current_step = wizard_state.get("step", 0)
        data: Dict[str, str] = wizard_state.setdefault("data", {})  # type: ignore[assignment]
        key = self.WIZARD_STEPS[current_step]
        data[key] = text
        wizard_state["step"] = current_step + 1
        if wizard_state["step"] >= len(self.WIZARD_STEPS):
            self._finalise_bank_wizard(update, context, data)
            self._chat_state(context, update.chat_id).pop("bank_wizard", None)
        else:
            self._prompt_bank_wizard(update, context)

    def _prompt_bank_wizard(self, update: Update, context: MutableMapping[str, object]) -> None:
        chat_state = self._chat_state(context, update.chat_id)
        wizard_state = chat_state["bank_wizard"]
        step_index = wizard_state["step"]
        step_key = self.WIZARD_STEPS[step_index]
        prompt_key = {
            "name": "wizard.bank.step.name",
            "account": "wizard.bank.step.account",
            "preferences": "wizard.bank.step.preferences",
        }[step_key]
        ui.render_screen(update.__dict__, context, translate(prompt_key, self.locale), None)

    def _finalise_bank_wizard(self, update: Update, context: MutableMapping[str, object], data: Dict[str, str]) -> None:
        chat_id = update.chat_id
        bank = Bank(
            identifier=self._next_id("bank"),
            name=data.get("name", "Без названия"),
            accounts=[data.get("account", "Основной")],
            preferences={"cashback": data.get("preferences", "")},
        )
        self.db.add_bank(chat_id, bank)
        self.db.add_experience(chat_id, 40)
        ui.render_screen(update.__dict__, context, translate("wizard.bank.completed", self.locale), None)
        self._render_main_menu(update, context)

    # ------------------------------------------------------------- templates -------
    def _render_templates(self, update: Update, context: MutableMapping[str, object]) -> None:
        templates = self.db.list_templates(update.chat_id)
        rows: List[List[ui.KeyboardButton]] = []
        for template in templates:
            rows.append(
                [
                    ui.KeyboardButton("✏️", ui.edit_callback(template.identifier)),
                    ui.KeyboardButton("🗑", ui.delete_callback(template.identifier)),
                ]
            )
        rows.append([ui.KeyboardButton(translate("templates.add", self.locale), ui.action_callback("templates:add"))])
        keyboard = ui.build_keyboard(rows)
        description = translate("templates.title", self.locale)
        ui.render_screen(update.__dict__, context, description, keyboard)

    def _start_template_edit(self, update: Update, context: MutableMapping[str, object], template_id: str) -> None:
        chat_state = self._chat_state(context, update.chat_id)
        chat_state["template_edit"] = {"id": template_id}
        ui.render_screen(update.__dict__, context, translate("templates.manual_prompt", self.locale), None)

    def _finalise_template_edit(self, update: Update, context: MutableMapping[str, object], edit_state: Dict[str, str]) -> None:
        template_id = edit_state["id"]
        text = (update.message_text or "").strip()
        templates = {tpl.identifier: tpl for tpl in self.db.list_templates(update.chat_id)}
        template = templates.get(template_id)
        if template:
            template.pattern = text
            self.db.add_template(update.chat_id, template)
            ui.render_screen(update.__dict__, context, ui.STATUS_MESSAGES["ready"], None)
        else:
            ui.render_screen(update.__dict__, context, ui.STATUS_MESSAGES["error"], None)
        self._chat_state(context, update.chat_id).pop("template_edit", None)
        self._render_templates(update, context)

    def _delete_template(self, update: Update, context: MutableMapping[str, object], template_id: str) -> None:
        chat_state = self._chat_state(context, update.chat_id)
        chat_state.pop("template_edit", None)
        self.db.remove_template(update.chat_id, template_id)
        ui.render_screen(update.__dict__, context, ui.STATUS_MESSAGES["ready"], None)
        self._render_templates(update, context)

    def _save_manual_template(self, update: Update, context: MutableMapping[str, object], text: str) -> None:
        template = Template(identifier=self._next_id("tpl"), name="Manual", pattern=text)
        self.db.add_template(update.chat_id, template)
        ui.render_screen(update.__dict__, context, ui.STATUS_MESSAGES["ready"], None)
        self._render_templates(update, context)

    # ------------------------------------------------------------- analytics -------
    def _show_pro_analytics(self, update: Update, context: MutableMapping[str, object]) -> None:
        self._push_indicator(context, update.chat_id, ui.TYPING_INDICATOR)
        ui.render_screen(update.__dict__, context, translate("analytics.processed", self.locale), None)
        transactions = self.db.list_transactions(update.chat_id)
        leaderboard = self.ranking.build_leaderboard(transactions)
        summary = translate("analytics.summary", self.locale, amount=round(self.db.monthly_cashback(update.chat_id), 2))
        details = "\n".join(f"{category}: {amount}" for category, amount in leaderboard) or "—"
        ui.render_screen(update.__dict__, context, f"{translate('analytics.title', self.locale)}\n{summary}\n{details}", None)

    def _show_recommendations(self, update: Update, context: MutableMapping[str, object]) -> None:
        self._push_indicator(context, update.chat_id, ui.TYPING_INDICATOR)
        ui.render_screen(update.__dict__, context, translate("status.processing", self.locale), None)
        recommendations = self.recommendation_engine.build(update.chat_id, self.db)
        lines = [translate("recommendations.title", self.locale)]
        lines.extend(f"• {rec.title}: {rec.description}" for rec in recommendations)
        ui.render_screen(update.__dict__, context, "\n".join(lines), None)

    def _show_history(self, update: Update, context: MutableMapping[str, object]) -> None:
        history = self.db.list_transactions(update.chat_id)
        if not history:
            ui.render_screen(update.__dict__, context, translate("empty.history", self.locale), None)
            return
        lines = [translate("history.title", self.locale)]
        for tx in history:
            lines.append(f"• {tx.category}: {tx.amount} ₽")
        ui.render_screen(update.__dict__, context, "\n".join(lines), None)

    def _show_gamification(self, update: Update, context: MutableMapping[str, object]) -> None:
        status = self.gamification_engine.build(update.chat_id, self.db)
        ui.render_screen(
            update.__dict__,
            context,
            translate("extensions.gamification.level", self.locale, level=status),
            None,
        )

    # ------------------------------------------------------------- notifications ---
    def _show_notifications(self, update: Update, context: MutableMapping[str, object]) -> None:
        settings = self.db.get_notifications(update.chat_id)
        buttons = ui.single_column(
            [
                ui.KeyboardButton(translate("notifications.mode.smart", self.locale), ui.action_callback("notifications:smart")),
                ui.KeyboardButton(translate("notifications.mode.weekly", self.locale), ui.action_callback("notifications:weekly")),
                ui.KeyboardButton(translate("notifications.mode.off", self.locale), ui.action_callback("notifications:off")),
            ]
        )
        message = f"{translate('notifications.title', self.locale)}\nТекущий режим: {settings.mode}"
        ui.render_screen(update.__dict__, context, message, buttons)

    def _update_notifications(self, update: Update, context: MutableMapping[str, object], mode: str) -> None:
        self.db.update_notifications(update.chat_id, mode=mode)
        if mode == "weekly":
            self.scheduler.schedule(update.chat_id, "digest", "weekly")
        elif mode == "smart":
            self.scheduler.schedule(update.chat_id, "smart", "smart")
        else:
            self.scheduler.cancel(update.chat_id, "digest")
            self.scheduler.cancel(update.chat_id, "smart")
        ui.render_screen(update.__dict__, context, ui.STATUS_MESSAGES["ready"], None)
        self._show_notifications(update, context)

    # ------------------------------------------------------------- receipt flow ----
    def _process_receipt(self, update: Update, context: MutableMapping[str, object]) -> None:
        self._push_indicator(context, update.chat_id, ui.TYPING_INDICATOR)
        ui.render_screen(update.__dict__, context, translate("status.processing", self.locale), None)
        ocr_result = self.ocr.recognise(b"fake", mode="smart")
        entities = self.nlp.extract_entities(ocr_result.text)
        intent = self.nlp.detect_intent(ocr_result.text)
        amount = 0.0
        if intent == "reward":
            amount = sum(float(item.get("amount", 0.0)) for item in ocr_result.items)
        for item in ocr_result.items:
            enriched = self.categories.enrich(item)
            transaction = Transaction(
                identifier=self._next_id("tx"),
                amount=float(enriched.get("amount", 0.0)),
                category=enriched.get("category", ""),
                bank_id="auto",
            )
            self.db.add_transaction(update.chat_id, transaction)
        self.db.add_experience(update.chat_id, 20)
        templates = self.nlp.recommend_templates(ocr_result.text)
        if templates:
            for template_key in templates:
                template = Template(identifier=self._next_id("tpl"), name=template_key, pattern="auto")
                self.db.add_template(update.chat_id, template)
        message = (
            f"OCR: {ocr_result.confidence}, intent={intent}, total={amount}, "
            f"merchants={','.join(entities['merchants'])}"
        )
        ui.render_screen(update.__dict__, context, message, None)
        self._render_main_menu(update, context)


__all__ = ["CashbackBot", "Update"]
