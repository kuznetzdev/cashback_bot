"""Wizard flow management for adding banks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List

from .categories import CategoryNormalizer
from .db import AsyncDatabase, WizardSession


@dataclass
class WizardData:
    user_id: int
    step: str = "select_bank"
    bank_id: int | None = None
    bank_name: str | None = None
    input_mode: str | None = None
    categories: list[dict[str, Any]] = field(default_factory=list)
    template_identifier: str | None = None


class WizardService:
    """Persist and orchestrate wizard sessions."""

    def __init__(self, db: AsyncDatabase, normalizer: CategoryNormalizer) -> None:
        self._db = db
        self._normalizer = normalizer

    async def load(self, user_id: int) -> WizardData:
        session = await self._db.get_wizard_session(user_id)
        if session is None:
            return WizardData(user_id=user_id)
        return self._from_session(session)

    async def start(self, user_id: int) -> WizardData:
        data = WizardData(user_id=user_id)
        await self._save(data)
        return data

    async def update(self, data: WizardData) -> None:
        await self._save(data)

    async def cancel(self, user_id: int) -> None:
        await self._db.delete_wizard_session(user_id)

    async def finalize(self, data: WizardData) -> int:
        if not data.bank_name:
            raise ValueError("Bank name is required for wizard finalization")
        if not data.categories:
            raise ValueError("At least one category is required to save the bank")
        user_bank_id = await self._db.create_user_bank(data.user_id, data.bank_name, data.bank_id)
        rows = []
        for entry in data.categories:
            name = entry.get("name")
            rate = float(entry.get("rate", 0.0))
            level = int(entry.get("level", 1))
            normalized = self._normalizer.normalize(name)
            rows.append((name, normalized, rate, level))
        await self._db.replace_bank_categories(user_bank_id, rows)
        await self._db.delete_wizard_session(data.user_id)
        return user_bank_id

    def parse_categories_text(self, text: str) -> List[dict[str, Any]]:
        categories: List[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            level = self._extract_level(line)
            cleaned = self._remove_level_markers(line)
            match = re.search(r"(.+?)[\s:=\-]+([0-9]+(?:[.,][0-9]{1,2})?)%?", cleaned)
            if not match:
                continue
            name = match.group(1).strip()
            rate = float(match.group(2).replace(",", ".")) / 100
            categories.append(
                {
                    "name": name,
                    "rate": rate,
                    "level": level,
                }
            )
        return categories

    def apply_template(self, payload: dict[str, Any]) -> List[dict[str, Any]]:
        fields = payload.get("fields", [])
        categories: List[dict[str, Any]] = []
        for field_name in fields:
            categories.append({"name": str(field_name), "rate": 0.0, "level": 1})
        return categories

    def _extract_level(self, text: str) -> int:
        level_match = re.search(r"L(\d)", text, re.IGNORECASE)
        if level_match:
            try:
                return int(level_match.group(1))
            except ValueError:
                return 1
        return 1

    def _remove_level_markers(self, text: str) -> str:
        return re.sub(r"L\d", "", text, flags=re.IGNORECASE)

    async def _save(self, data: WizardData) -> None:
        payload = {
            "step": data.step,
            "bank_id": data.bank_id,
            "bank_name": data.bank_name,
            "input_mode": data.input_mode,
            "categories": data.categories,
            "template_identifier": data.template_identifier,
        }
        await self._db.save_wizard_session(data.user_id, data.step, payload)

    def _from_session(self, session: WizardSession) -> WizardData:
        payload = session.payload
        return WizardData(
            user_id=session.user_id,
            step=str(payload.get("step", session.state)),
            bank_id=payload.get("bank_id"),
            bank_name=payload.get("bank_name"),
            input_mode=payload.get("input_mode"),
            categories=list(payload.get("categories", [])),
            template_identifier=payload.get("template_identifier"),
        )

