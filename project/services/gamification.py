"""Gamification utilities for the cashback bot."""
from __future__ import annotations

from dataclasses import dataclass

from .db import AsyncDatabase


@dataclass(frozen=True)
class GamificationProfile:
    points: int
    level: str


class GamificationService:
    """Manage points and levels for user actions."""

    ACTION_POINTS: dict[str, int] = {
        "add_bank": 1,
        "update_bank": 1,
        "manual_edit": 2,
    }

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def award(self, user_id: int, action: str) -> GamificationProfile:
        points = self.ACTION_POINTS.get(action, 0)
        total_points, level = await self._db.increment_points(user_id, points)
        return GamificationProfile(points=total_points, level=level)

    async def profile(self, user_id: int) -> GamificationProfile:
        profile = await self._db.fetch_user_profile(user_id)
        if not profile:
            return GamificationProfile(points=0, level="Bronze")
        return GamificationProfile(points=int(profile["points"]), level=str(profile["level"]))

