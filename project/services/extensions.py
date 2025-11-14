"""Extensibility hooks for advanced features."""
from __future__ import annotations

from typing import Callable, List

from .db import Transaction


class ExtensionRegistry:
    def __init__(self) -> None:
        self._recommendation_hooks: List[Callable[[List[Transaction]], List[str]]] = []

    def register_recommendation_hook(
        self, hook: Callable[[List[Transaction]], List[str]]
    ) -> None:
        self._recommendation_hooks.append(hook)

    def build_recommendations(self, transactions: List[Transaction]) -> List[str]:
        recommendations: List[str] = []
        for hook in self._recommendation_hooks:
            recommendations.extend(hook(transactions))
        return recommendations


def default_recommendation_hook(transactions: List[Transaction]) -> List[str]:
    tips: List[str] = []
    if any(t.amount > 1000 for t in transactions):
        tips.append("Попробуйте оплату частями, чтобы увеличить кэшбэк")
    if not tips:
        tips.append("Следите за акциями банков, чтобы повысить выгоду")
    return tips
