from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from project.bot import CashbackBot, Update
from project.i18n.translations import translate
from project.services import ui
from project.services.categories import CategoryService
from project.services.db import Database
from project.services.extensions import GamificationEngine, RecommendationEngine
from project.services.nlp import NlpService
from project.services.ocr import OcrService
from project.services.ranking import RankingService
from project.services.scheduler import SchedulerService


def build_bot() -> CashbackBot:
    db = Database()
    ocr = OcrService()
    nlp = NlpService()
    categories = CategoryService()
    ranking = RankingService()
    scheduler = SchedulerService()
    recommendation_engine = RecommendationEngine()
    gamification_engine = GamificationEngine()
    return CashbackBot(db, ocr, nlp, categories, ranking, scheduler, recommendation_engine, gamification_engine)


def test_bank_wizard_flow() -> None:
    bot = build_bot()
    context: dict[str, object] = {}
    bot.start(Update(chat_id=1), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.nav_callback("add_bank")), context)
    bot.handle_message(Update(chat_id=1, message_text="Тинькофф"), context)
    bot.handle_message(Update(chat_id=1, message_text="Основной счёт"), context)
    bot.handle_message(Update(chat_id=1, message_text="Топ категории"), context)

    db = bot.db
    banks = db.list_banks(1)
    assert len(banks) == 1
    assert banks[0].name == "Тинькофф"
    assert banks[0].accounts == ["Основной счёт"]


def test_manual_template_cycle() -> None:
    bot = build_bot()
    context: dict[str, object] = {}
    bot.start(Update(chat_id=1), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.nav_callback("manual_templates")), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.action_callback("templates:add")), context)
    bot.handle_message(Update(chat_id=1, message_text="Шаблон №1"), context)

    templates = bot.db.list_templates(1)
    assert templates
    template_id = templates[0].identifier

    bot.handle_callback(Update(chat_id=1, callback_data=ui.edit_callback(template_id)), context)
    bot.handle_message(Update(chat_id=1, message_text="Обновлённый шаблон"), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.delete_callback(template_id)), context)

    assert not bot.db.list_templates(1)


def test_process_receipt_and_notifications() -> None:
    bot = build_bot()
    context: dict[str, object] = {}
    bot.start(Update(chat_id=1), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.action_callback("process:receipt")), context)

    assert bot.db.list_transactions(1)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.nav_callback("pro_analytics")), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.nav_callback("notifications")), context)
    bot.handle_callback(Update(chat_id=1, callback_data=ui.action_callback("notifications:weekly")), context)

    jobs = bot.scheduler.list_jobs(1)
    assert any(job.job_type == "digest" for job in jobs)

    bot.handle_callback(Update(chat_id=1, callback_data=ui.nav_callback("recommendations")), context)
    messages = context.get("ui_messages", [])
    assert any(translate("recommendations.title") in message.text for message in messages)
