from pathlib import Path
import sys
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.bot import CashbackBot
from project.services.db import InMemoryDB
from project.services.scheduler import SchedulerService, ScheduledNotification


class ListScheduler:
    """Test double emulating an append-only scheduler."""

    def __init__(self) -> None:
        self._entries: Dict[int, List[ScheduledNotification]] = {}

    def schedule(self, user_id: int, mode: str, hour: int) -> ScheduledNotification:
        entry = ScheduledNotification(user_id=user_id, mode=mode, hour=hour)
        self._entries.setdefault(user_id, []).append(entry)
        return entry

    def cancel(self, user_id: int, mode: Optional[str] = None) -> None:
        if mode is None:
            self._entries.pop(user_id, None)
            return
        entries = self._entries.get(user_id)
        if not entries:
            return
        remaining = [entry for entry in entries if entry.mode != mode]
        if remaining:
            self._entries[user_id] = remaining
        else:
            self._entries.pop(user_id, None)

    def list_all(self) -> List[ScheduledNotification]:
        return [entry for entries in self._entries.values() for entry in entries]


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
    scheduler = SchedulerService()
    bot = CashbackBot(db=InMemoryDB(), scheduler=scheduler)
    notifications_screen = bot.handle_callback(user_id=1, callback_data="nav:notifications")
    callbacks = extract_callback_data(notifications_screen)
    assert "action:enable_smart_notifications" in callbacks

    response = bot.handle_callback(user_id=1, callback_data="action:enable_weekly_notifications")
    assert "weekly" in response["text"]
    entries = scheduler.list_all()
    assert len(entries) == 1
    assert entries[0].mode == "weekly"

    response = bot.handle_callback(user_id=1, callback_data="action:enable_smart_notifications")
    assert "smart" in response["text"]
    entries = scheduler.list_all()
    assert len(entries) == 1
    assert entries[0].mode == "smart"


def test_notifications_reschedule_clears_duplicates():
    scheduler = ListScheduler()
    bot = CashbackBot(db=InMemoryDB(), scheduler=scheduler)

    bot.handle_callback(user_id=1, callback_data="action:enable_weekly_notifications")
    bot.handle_callback(user_id=1, callback_data="action:enable_weekly_notifications")
    entries = scheduler.list_all()
    assert len(entries) == 1
    assert entries[0].mode == "weekly"

    bot.handle_callback(user_id=1, callback_data="action:enable_smart_notifications")
    entries = scheduler.list_all()
    assert len(entries) == 1
    assert entries[0].mode == "smart"
