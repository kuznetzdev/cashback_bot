from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class UserProfile:
    id: int
    external_user_id: int
    username: str | None
    full_name: str | None
    language: str
    notifications_enabled: bool


@dataclass(slots=True)
class CashbackDraftItem:
    raw_category: str
    normalized_category: str
    percent: Decimal
    source_type: str


@dataclass(slots=True)
class Bank:
    id: int
    user_id: int
    bank_name: str


@dataclass(slots=True)
class BankAggregate:
    bank: Bank
    items: list[CashbackDraftItem] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedCategory:
    slug: str
    display_ru: str
    display_en: str


@dataclass(slots=True)
class CategoryLeader:
    category_slug: str
    category_name: str
    best_percent: Decimal
    bank_names: list[str]


@dataclass(slots=True)
class BankScore:
    bank_name: str
    score: int


@dataclass(slots=True)
class UserLogEntry:
    id: int
    user_id: int
    action: str
    payload: dict | None
    created_at: datetime


@dataclass(slots=True)
class DeleteIntent:
    kind: str
    target: str


@dataclass(slots=True)
class BestQueryIntent:
    normalized_category: str
