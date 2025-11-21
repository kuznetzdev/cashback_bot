from __future__ import annotations

"""NLP service for category synonyms and intent understanding."""
import re
from typing import Iterable, List, Optional

from ..models.item import CashbackItem
from .nlp_intents import Intent, IntentBuilder


class NLPService:
    def __init__(self) -> None:
        self._intent_builder = IntentBuilder()
        self._synonyms = {
            "азс": {"заправка", "топливо", "fuel"},
            "супермаркеты": {"магазины", "продукты", "groceries"},
            "рестораны": {"кафе", "общепит", "restaurants"},
            "аптеки": {"лекарства", "pharmacy"},
            "путешествия": {"travel", "авиабилеты", "отели"},
        }

    def normalize_category(self, name: str) -> str:
        key = name.strip().lower()
        for canonical, synonyms in self._synonyms.items():
            if key == canonical or key in synonyms:
                return canonical
        return key

    def expand_synonyms(self, categories: Iterable[CashbackItem]) -> List[CashbackItem]:
        expanded: List[CashbackItem] = []
        for item in categories:
            canonical = self.normalize_category(item.category)
            expanded.append(item.copy(update={"category": canonical}))
        return expanded

    def understand_delete_command(self, text: str) -> Optional[str]:
        match = re.search(r"удали\s+(?P<target>[\w\s]+)", text, re.IGNORECASE)
        if match:
            return match.group("target").strip()
        return None

    def understand_best_query(self, text: str) -> Optional[str]:
        match = re.search(r"(лучший|где лучше всего)\s+(?P<category>[\w\s]+)", text, re.IGNORECASE)
        if match:
            return match.group("category").strip()
        return None

    def build_intent(self, text: str) -> Optional[Intent]:
        return self._intent_builder.build(text)
