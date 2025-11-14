from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from project.services.analytics import AnalyticsService
from project.services.categories import CategoryNormalizer
from project.services.db import AsyncDatabase
from project.services.gamification import GamificationService
from project.services.recommendations import RecommendationService
from project.services.wizard import WizardService


@pytest.mark.asyncio
async def test_wizard_parse_and_finalize(tmp_path: Path) -> None:
    db = AsyncDatabase(tmp_path / "wizard.sqlite3")
    await db.init()
    normalizer = CategoryNormalizer()
    wizard = WizardService(db, normalizer)
    user_id = await db.upsert_user(telegram_id=1, language="en")
    categories = wizard.parse_categories_text("Groceries - 5%\nL2 Travel - 3.5%")
    assert categories[0]["name"].lower() == "groceries"
    data = await wizard.start(user_id)
    data.bank_name = "Test Bank"
    data.categories = categories
    bank_id = await wizard.finalize(data)
    stored = await db.fetch_bank_categories(bank_id)
    assert stored
    assert stored[0].normalized_name == "groceries"


@pytest.mark.asyncio
async def test_analytics_and_recommendations(tmp_path: Path) -> None:
    db = AsyncDatabase(tmp_path / "analytics.sqlite3")
    await db.init()
    normalizer = CategoryNormalizer()
    analytics = AnalyticsService(db, normalizer)
    recommendations = RecommendationService(db, normalizer)
    user_id = await db.upsert_user(telegram_id=42, language="en")
    bank_a = await db.create_user_bank(user_id, "Bank A")
    bank_b = await db.create_user_bank(user_id, "Bank B")
    await db.replace_bank_categories(
        bank_a,
        [("Groceries", normalizer.normalize("Groceries"), 0.05, 1)],
    )
    await db.replace_bank_categories(
        bank_b,
        [
            ("Travel", normalizer.normalize("Travel"), 0.02, 1),
            ("Groceries", normalizer.normalize("Groceries"), 0.01, 2),
        ],
    )
    worst = await analytics.top_worst_categories(user_id)
    assert worst and worst[0].rate <= 0.01
    buckets = await analytics.top_by_buckets(user_id)
    assert "5-9%" in buckets
    strengths = await analytics.bank_strength_score(user_id)
    assert strengths and strengths[0].bank_name in {"Bank A", "Bank B"}
    best = await recommendations.recommend_best_card_for(user_id, "groceries")
    assert best and "Bank A" in best.details
    move = await recommendations.recommend_where_to_move_cashback(user_id)
    assert move and move.details in {"Bank A", "Bank B"}


@pytest.mark.asyncio
async def test_gamification_points(tmp_path: Path) -> None:
    db = AsyncDatabase(tmp_path / "points.sqlite3")
    await db.init()
    gamification = GamificationService(db)
    user_id = await db.upsert_user(telegram_id=5, language="en")
    profile = await gamification.award(user_id, "add_bank")
    assert profile.points == 1
    profile = await gamification.award(user_id, "manual_edit")
    assert profile.points == 3
    current = await gamification.profile(user_id)
    assert current.points == 3
