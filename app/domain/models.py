from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class UserAccount:
    id: int
    display_name: str
    language: str
    notifications_enabled: bool

@dataclass(slots=True)
class UserIdentity:
    id: int
    user_id: int
    provider: str
    provider_user_id: str
    provider_username: str | None
    provider_display_name: str | None


@dataclass(slots=True)
class LocalCredentials:
    id: int
    user_id: int
    username: str
    email: str | None
    password_hash: str


@dataclass(slots=True)
class DeliveryTarget:
    user_id: int
    provider: str
    destination: str
    language: str


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
    target_month: str | None = None
    available_months: list[str] = field(default_factory=list)


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
