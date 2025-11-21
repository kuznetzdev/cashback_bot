from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cashback_bot.models.item import CashbackItem
from cashback_bot.services.nlp_intents import IntentBuilder
from cashback_bot.services.queue import QueueTask, WorkflowQueue
from cashback_bot.services.ranking import RankingService
from cashback_bot.services.storage import StorageService


@pytest.mark.asyncio
async def test_storage_schema(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "db.sqlite3")
    await storage.init_schema()
    user_id = await storage.upsert_user(telegram_id=1, locale="ru")
    assert user_id == 1
    history = await storage.list_history(user_id)
    assert history == []


def test_intents_parsing() -> None:
    builder = IntentBuilder()
    intent = builder.build("удали супермаркеты")
    assert intent and intent.type == "delete_category"
    edit = builder.build("измени процент у АЗС на 7%")
    assert edit and edit.payload["rate"] == 7.0
    best = builder.build("лучший кэшбек на рестораны")
    assert best and best.type == "best_query"


def test_ranking_suggestions() -> None:
    ranking = RankingService()
    items = [
        CashbackItem(category="АЗС", rate=5, bank="A"),
        CashbackItem(category="АЗС", rate=2, bank="B"),
        CashbackItem(category="Супермаркеты", rate=3, bank="A"),
    ]
    best, total = ranking.best_overall_bank(items)
    assert best == "A"
    assert total > 0
    gaps = ranking.highlight_gaps(items, threshold=2.0)
    assert "азс" in gaps
    suggestions = ranking.suggestions(items)
    assert any("B" in line for line in suggestions)


@pytest.mark.asyncio
async def test_queue_per_user_isolation() -> None:
    queue = WorkflowQueue()
    await queue.enqueue(QueueTask(user_id=1, bank_name="A", image_bytes=b"12345"))
    await queue.enqueue(QueueTask(user_id=2, bank_name="B", image_bytes=b"12345"))
    assert await queue.has_pending(1)
    task = await queue.next_task(1)
    assert task and task.user_id == 1
    other = await queue.next_task(2)
    assert other and other.user_id == 2
