"""Template management for manual category entry."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .db import AsyncDatabase, TemplateRecord


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    title_i18n: dict[str, str]
    fields: list[str]


@dataclass(frozen=True)
class TemplateView:
    identifier: str
    title: str
    payload: dict[str, Any]
    is_default: bool


DEFAULT_TEMPLATES: tuple[TemplateDefinition, ...] = (
    TemplateDefinition(
        key="standard",
        title_i18n={"en": "Standard categories", "ru": "Стандартные категории"},
        fields=[
            "Supermarkets",
            "Gas stations",
            "Transport",
            "Restaurants",
            "Pharmacy",
        ],
    ),
    TemplateDefinition(
        key="cashback_level_1",
        title_i18n={"en": "Cashback level 1", "ru": "Кэшбэк 1 уровня"},
        fields=["Level 1: Essentials", "Level 1: Everyday", "Level 1: Bonus"],
    ),
    TemplateDefinition(
        key="cashback_level_2",
        title_i18n={"en": "Cashback level 2", "ru": "Кэшбэк 2 уровня"},
        fields=["Level 2: Travel", "Level 2: Premium", "Level 2: Seasonal"],
    ),
    TemplateDefinition(
        key="bank_table",
        title_i18n={"en": "Bank table", "ru": "Банковская таблица"},
        fields=["Category A", "Category B", "Category C", "Category D"],
    ),
    TemplateDefinition(
        key="empty",
        title_i18n={"en": "Empty template", "ru": "Пустой шаблон"},
        fields=[],
    ),
)


class TemplateService:
    """High-level management of default and user templates."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def list_templates(self, user_id: int, locale: str) -> list[TemplateView]:
        user_templates = await self._db.list_templates(user_id)
        views: list[TemplateView] = []
        for definition in DEFAULT_TEMPLATES:
            views.append(
                TemplateView(
                    identifier=f"default:{definition.key}",
                    title=definition.title_i18n.get(locale, definition.title_i18n["en"]),
                    payload=self._build_payload(definition.fields),
                    is_default=True,
                )
            )
        for record in user_templates:
            payload = self._safe_payload(record)
            views.append(
                TemplateView(
                    identifier=f"user:{record.id}",
                    title=record.name,
                    payload=payload,
                    is_default=False,
                )
            )
        return views

    async def upsert_template(
        self,
        user_id: int,
        template_type: str,
        name: str,
        payload: dict[str, Any],
        template_id: int | None = None,
    ) -> int:
        return await self._db.upsert_template(user_id, template_type, name, payload, template_id)

    async def delete_template(self, user_id: int, template_id: int) -> None:
        await self._db.delete_template(user_id, template_id)

    def _safe_payload(self, record: TemplateRecord) -> dict[str, Any]:
        try:
            return json.loads(record.payload)
        except Exception:  # pragma: no cover - malformed payloads
            return self._build_payload([])

    @staticmethod
    def _build_payload(fields: Iterable[str]) -> dict[str, Any]:
        return {"fields": [str(field) for field in fields]}

