from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import pytest

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.models import Bank, CashbackDraftItem, UserLogEntry, UserProfile


@dataclass(slots=True)
class InMemoryStore:
    next_user_id: int = 1
    next_bank_id: int = 1
    next_log_id: int = 1
    users: dict[int, UserProfile] = field(default_factory=dict)
    users_by_external: dict[int, int] = field(default_factory=dict)
    banks: dict[int, Bank] = field(default_factory=dict)
    bank_items: dict[int, list[CashbackDraftItem]] = field(default_factory=dict)
    logs: list[UserLogEntry] = field(default_factory=list)


class InMemoryUsersRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def upsert(
        self,
        *,
        external_user_id: int,
        username: str | None,
        full_name: str | None,
        default_language: str,
    ) -> UserProfile:
        internal_id = self.store.users_by_external.get(external_user_id)
        if internal_id is None:
            user = UserProfile(
                id=self.store.next_user_id,
                external_user_id=external_user_id,
                username=username,
                full_name=full_name,
                language=default_language,
                notifications_enabled=True,
            )
            self.store.users[user.id] = user
            self.store.users_by_external[external_user_id] = user.id
            self.store.next_user_id += 1
            return user
        user = self.store.users[internal_id]
        user.username = username
        user.full_name = full_name
        return user

    async def get_by_external_id(self, external_user_id: int) -> UserProfile | None:
        internal_id = self.store.users_by_external.get(external_user_id)
        if internal_id is None:
            return None
        return self.store.users.get(internal_id)

    async def get_by_id(self, user_id: int) -> UserProfile | None:
        return self.store.users.get(user_id)

    async def set_language(self, user_id: int, language: str) -> None:
        user = self.store.users.get(user_id)
        if user is not None:
            user.language = language

    async def toggle_notifications(self, user_id: int) -> bool:
        user = self.store.users.get(user_id)
        if user is None:
            return False
        user.notifications_enabled = not user.notifications_enabled
        return user.notifications_enabled

    async def list_notification_enabled(self) -> list[UserProfile]:
        return [user for user in self.store.users.values() if user.notifications_enabled]


class InMemoryBanksRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def list_for_user(self, user_id: int) -> list[Bank]:
        return sorted(
            [bank for bank in self.store.banks.values() if bank.user_id == user_id],
            key=lambda item: item.bank_name.lower(),
        )

    async def get_for_user(self, user_id: int, bank_id: int) -> Bank | None:
        bank = self.store.banks.get(bank_id)
        if bank is None or bank.user_id != user_id:
            return None
        return bank

    async def get_by_name(self, user_id: int, bank_name: str) -> Bank | None:
        lowered = bank_name.strip().lower()
        for bank in self.store.banks.values():
            if bank.user_id == user_id and bank.bank_name.lower() == lowered:
                return bank
        return None

    async def create(self, user_id: int, bank_name: str) -> Bank:
        bank = Bank(id=self.store.next_bank_id, user_id=user_id, bank_name=bank_name.strip())
        self.store.banks[bank.id] = bank
        self.store.next_bank_id += 1
        return bank

    async def update_name(self, bank_id: int, bank_name: str) -> None:
        bank = self.store.banks.get(bank_id)
        if bank is not None:
            bank.bank_name = bank_name.strip()

    async def delete(self, bank_id: int) -> None:
        self.store.banks.pop(bank_id, None)
        self.store.bank_items.pop(bank_id, None)


class InMemoryCashbackRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def list_for_bank(self, bank_id: int) -> list[CashbackDraftItem]:
        return list(self.store.bank_items.get(bank_id, []))

    async def replace_for_bank(self, bank_id: int, items: list[CashbackDraftItem]) -> None:
        self.store.bank_items[bank_id] = list(items)


class InMemoryLogsRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def add(self, user_id: int, action: str, payload: dict | None = None) -> None:
        entry = UserLogEntry(
            id=self.store.next_log_id,
            user_id=user_id,
            action=action,
            payload=payload,
            created_at=datetime.now(),
        )
        self.store.next_log_id += 1
        self.store.logs.append(entry)

    async def list_recent(self, user_id: int, limit: int) -> list[UserLogEntry]:
        items = [entry for entry in self.store.logs if entry.user_id == user_id]
        return sorted(items, key=lambda entry: entry.created_at, reverse=True)[:limit]

    async def list_action_since(self, user_id: int, action: str, since: datetime) -> list[UserLogEntry]:
        return [
            entry
            for entry in self.store.logs
            if entry.user_id == user_id and entry.action == action and entry.created_at >= since
        ]


class InMemoryUnitOfWork(UnitOfWorkPort):
    def __init__(self, store: InMemoryStore) -> None:
        self.users = InMemoryUsersRepo(store)
        self.banks = InMemoryBanksRepo(store)
        self.cashback = InMemoryCashbackRepo(store)
        self.logs = InMemoryLogsRepo(store)

    async def __aenter__(self) -> "InMemoryUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.fixture()
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture()
def uow_factory(store: InMemoryStore) -> Callable[[], InMemoryUnitOfWork]:
    def factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    return factory


class DummyOCR:
    def __init__(self) -> None:
        self.value = "АЗС 5%"

    async def extract_text(self, image_path) -> str:
        _ = image_path
        return self.value


@pytest.fixture()
def dummy_ocr() -> DummyOCR:
    return DummyOCR()
