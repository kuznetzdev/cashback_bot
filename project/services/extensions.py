"""Convenience wrappers for the recommendation engine."""
from __future__ import annotations

from typing import Optional

from telegram.ext import ContextTypes

from .recommendations import Recommendation, RecommendationService


def _resolve_engine(context: ContextTypes.DEFAULT_TYPE) -> RecommendationService:
    engine: RecommendationService = context.application.bot_data["recommendations"]
    return engine


async def recommend_best_card_for(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, category: str
) -> Optional[Recommendation]:
    """Return the best card for a given category."""

    return await _resolve_engine(context).recommend_best_card_for(user_id, category)


async def recommend_what_to_update(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, bank_id: int
) -> list[Recommendation]:
    """Suggest categories that need updates for a bank."""

    return await _resolve_engine(context).recommend_what_to_update(user_id, bank_id)


async def recommend_where_to_move_cashback(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> Optional[Recommendation]:
    """Suggest where to move cashback for better rate."""

    return await _resolve_engine(context).recommend_where_to_move_cashback(user_id)


async def recommend_new_category_opportunities(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> list[Recommendation]:
    """Find categories with low coverage that can be improved."""

    return await _resolve_engine(context).recommend_new_category_opportunities(user_id)

