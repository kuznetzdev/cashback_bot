from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.bot import CashbackBot
from project.services.db import InMemoryDB


def extract_callback_data(message):
    return [button["callback_data"] for row in message["keyboard"] for button in row]


def test_start_displays_main_menu():
    bot = CashbackBot(db=InMemoryDB())
    response = bot.handle_start(user_id=1)
    callbacks = extract_callback_data(response)
    assert "nav:analytics" in callbacks
    assert "nav:bank_wizard" in callbacks


def test_bank_wizard_flow():
    bot = CashbackBot(db=InMemoryDB())
    bot.handle_callback(user_id=1, callback_data="nav:bank_wizard")
    response = bot.handle_wizard_input(user_id=1, text="Тинькофф")
    callbacks = extract_callback_data(response)
    assert "action:set_product_debit" in callbacks

    response = bot.handle_callback(user_id=1, callback_data="action:set_product_debit")
    callbacks = extract_callback_data(response)
    assert "action:confirm_bank" in callbacks

    response = bot.handle_callback(user_id=1, callback_data="action:confirm_bank")
    callbacks = extract_callback_data(response)
    assert "nav:analytics" in callbacks


def test_template_management_cycle():
    bot = CashbackBot(db=InMemoryDB())
    bot.handle_callback(user_id=1, callback_data="nav:templates")
    bot.handle_callback(user_id=1, callback_data="action:add_template")

    templates_screen = bot.handle_callback(user_id=1, callback_data="nav:templates")
    callbacks = extract_callback_data(templates_screen)
    edit_callbacks = [data for data in callbacks if data.startswith("edit:template_")]
    delete_callbacks = [data for data in callbacks if data.startswith("del:template_")]
    assert edit_callbacks and delete_callbacks

    bot.handle_callback(user_id=1, callback_data=delete_callbacks[0])
    after_delete = bot.handle_callback(user_id=1, callback_data="nav:templates")
    assert "del:template_" not in " ".join(extract_callback_data(after_delete))


def test_receipt_processing_updates_analytics_and_recommendations():
    bot = CashbackBot(db=InMemoryDB())
    payload = "Кафе Супер кофе 250.50\nАптека здоровье 900".encode("utf-8")
    response = bot.process_receipt(user_id=1, image_payload=payload)
    assert "📊 Обновленная аналитика" in response["text"]

    recommendations_screen = bot.handle_callback(user_id=1, callback_data="nav:recommendations")
    assert "рекомендации" in recommendations_screen["text"].lower()

    gamification_screen = bot.handle_callback(user_id=1, callback_data="nav:gamification")
    assert "🏆" in gamification_screen["text"]


def test_notifications_schedule():
    bot = CashbackBot(db=InMemoryDB())
    bot.handle_callback(user_id=1, callback_data="nav:notifications")
    response = bot.handle_callback(user_id=1, callback_data="action:enable_weekly_notifications")
    assert "weekly" in response["text"]
