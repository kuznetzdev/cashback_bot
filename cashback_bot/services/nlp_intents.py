from __future__ import annotations

"""Intent builder for natural-language commands."""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Intent:
    type: str
    payload: dict


class IntentBuilder:
    DELETE_RE = re.compile(r"удали\s+(?P<target>[\w\s]+)", re.IGNORECASE)
    BEST_RE = re.compile(r"(лучший|где лучше всего)\s+(?P<category>[\w\s]+)", re.IGNORECASE)
    EDIT_RATE_RE = re.compile(r"измени\s+процент\s+у\s+(?P<category>[\w\s]+)\s+на\s+(?P<rate>\d+[\.,]?\d*)%?", re.IGNORECASE)
    CHECK_BEST_RE = re.compile(r"проверь\s+мои\s+лучшие\s+категории", re.IGNORECASE)

    def build(self, text: str) -> Optional[Intent]:
        text = text.strip()
        edit_match = self.EDIT_RATE_RE.search(text)
        if edit_match:
            return Intent(
                type="edit_percent",
                payload={
                    "category": edit_match.group("category").strip(),
                    "rate": float(edit_match.group("rate").replace(",", ".")),
                },
            )
        delete_match = self.DELETE_RE.search(text)
        if delete_match:
            return Intent(type="delete_category", payload={"category": delete_match.group("target").strip()})
        best_match = self.BEST_RE.search(text)
        if best_match:
            return Intent(type="best_query", payload={"category": best_match.group("category").strip()})
        if self.CHECK_BEST_RE.search(text):
            return Intent(type="best_overview", payload={})
        return None
