"""Additional business logic for recommendations and gamification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from project.services.db import Database


@dataclass
class Recommendation:
    title: str
    description: str


class RecommendationEngine:
    """Generates recommendations based on analytics context."""

    def build(self, chat_id: int, db: Database) -> List[Recommendation]:
        total_cashback = db.monthly_cashback(chat_id)
        if total_cashback > 1000:
            return [
                Recommendation(
                    title="Повысьте лимит",
                    description="Вы приближаетесь к лимиту кешбэка, рассмотрите премиум карту.",
                )
            ]
        return [
            Recommendation(
                title="Активируйте спецпредложение",
                description="Доступна акция в партнёрских супермаркетах.",
            )
        ]


class GamificationEngine:
    """Calculates gamification progress messages."""

    def build(self, chat_id: int, db: Database) -> str:
        state = db.get_gamification(chat_id)
        return f"Level {state.level} ({state.experience}/100 XP)"


__all__ = ["Recommendation", "RecommendationEngine", "GamificationEngine"]
