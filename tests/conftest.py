from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import pytest

from app.application.months import current_month_key, sort_month_keys
from app.application.contracts.ports import UnitOfWorkPort
from app.application.dto.media import ImageUpload
from app.application.workflow.models import WorkflowState
from app.domain.models import Bank, CashbackDraftItem, DeliveryTarget, LocalCredentials, UserAccount, UserIdentity, UserLogEntry


@dataclass(slots=True)
class InMemoryStore:
    next_user_id: int = 1
    next_identity_id: int = 1
    next_credentials_id: int = 1
    next_bank_id: int = 1
    next_log_id: int = 1
    users: dict[int, UserAccount] = field(default_factory=dict)
    identities: dict[int, UserIdentity] = field(default_factory=dict)
    identity_index: dict[tuple[str, str], int] = field(default_factory=dict)
    credentials: dict[int, LocalCredentials] = field(default_factory=dict)
    credentials_by_username: dict[str, int] = field(default_factory=dict)
    credentials_by_email: dict[str, int] = field(default_factory=dict)
    banks: dict[int, Bank] = field(default_factory=dict)
    bank_items: dict[int, dict[str, list[CashbackDraftItem]]] = field(default_factory=dict)
    logs: list[UserLogEntry] = field(default_factory=list)
    workflow_states: dict[int, dict[str, object]] = field(default_factory=dict)


class InMemoryUsersRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create(self, *, display_name: str, default_language: str) -> UserAccount:
        user = UserAccount(
            id=self.store.next_user_id,
            display_name=display_name.strip(),
            language=default_language,
            notifications_enabled=True,
        )
        self.store.users[user.id] = user
        self.store.next_user_id += 1
        return user

    async def get_by_id(self, user_id: int) -> UserAccount | None:
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

    async def list_notification_enabled(self) -> list[UserAccount]:
        return [user for user in self.store.users.values() if user.notifications_enabled]


class InMemoryIdentitiesRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def get_by_provider_identity(self, *, provider: str, provider_user_id: str) -> UserIdentity | None:
        identity_id = self.store.identity_index.get((provider, provider_user_id))
        if identity_id is None:
            return None
        return self.store.identities.get(identity_id)

    async def list_for_user(self, user_id: int) -> list[UserIdentity]:
        return sorted(
            [identity for identity in self.store.identities.values() if identity.user_id == user_id],
            key=lambda item: item.provider,
        )

    async def count_for_user(self, user_id: int) -> int:
        return len([identity for identity in self.store.identities.values() if identity.user_id == user_id])

    async def upsert_for_user(
        self,
        *,
        user_id: int,
        provider: str,
        provider_user_id: str,
        provider_username: str | None,
        provider_display_name: str | None,
    ) -> UserIdentity:
        existing = next(
            (
                identity
                for identity in self.store.identities.values()
                if identity.user_id == user_id and identity.provider == provider
            ),
            None,
        )
        if existing is None:
            identity = UserIdentity(
                id=self.store.next_identity_id,
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_username=provider_username,
                provider_display_name=provider_display_name,
            )
            self.store.identities[identity.id] = identity
            self.store.next_identity_id += 1
        else:
            self.store.identity_index.pop((existing.provider, existing.provider_user_id), None)
            existing.provider_user_id = provider_user_id
            existing.provider_username = provider_username
            existing.provider_display_name = provider_display_name
            identity = existing
        self.store.identity_index[(provider, provider_user_id)] = identity.id
        return identity

    async def remove_for_user(self, *, user_id: int, provider: str) -> bool:
        identity = next(
            (
                item
                for item in self.store.identities.values()
                if item.user_id == user_id and item.provider == provider
            ),
            None,
        )
        if identity is None:
            return False
        self.store.identity_index.pop((identity.provider, identity.provider_user_id), None)
        self.store.identities.pop(identity.id, None)
        return True

    async def list_delivery_targets(self, *, provider: str) -> list[DeliveryTarget]:
        targets: list[DeliveryTarget] = []
        for identity in self.store.identities.values():
            if identity.provider != provider:
                continue
            user = self.store.users.get(identity.user_id)
            if user is None or not user.notifications_enabled:
                continue
            targets.append(
                DeliveryTarget(
                    user_id=user.id,
                    provider=identity.provider,
                    destination=identity.provider_user_id,
                    language=user.language,
                )
            )
        return targets


class InMemoryCredentialsRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def create(
        self,
        *,
        user_id: int,
        username: str,
        email: str | None,
        password_hash: str,
    ) -> LocalCredentials:
        credentials = LocalCredentials(
            id=self.store.next_credentials_id,
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
        )
        self.store.credentials[credentials.id] = credentials
        self.store.credentials_by_username[username] = credentials.id
        if email is not None:
            self.store.credentials_by_email[email] = credentials.id
        self.store.next_credentials_id += 1
        return credentials

    async def get_by_username(self, username: str) -> LocalCredentials | None:
        credentials_id = self.store.credentials_by_username.get(username)
        if credentials_id is None:
            return None
        return self.store.credentials.get(credentials_id)

    async def get_by_email(self, email: str) -> LocalCredentials | None:
        credentials_id = self.store.credentials_by_email.get(email)
        if credentials_id is None:
            return None
        return self.store.credentials.get(credentials_id)

    async def get_by_user_id(self, user_id: int) -> LocalCredentials | None:
        return next((item for item in self.store.credentials.values() if item.user_id == user_id), None)

    async def has_for_user(self, user_id: int) -> bool:
        return any(item.user_id == user_id for item in self.store.credentials.values())


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

    async def list_for_bank(self, bank_id: int, target_month: str | None = None) -> list[CashbackDraftItem]:
        month = target_month or current_month_key()
        bank_months = self.store.bank_items.get(bank_id, {})
        return list(bank_months.get(month, []))

    async def replace_for_bank(self, bank_id: int, target_month: str, items: list[CashbackDraftItem]) -> None:
        bank_months = self.store.bank_items.setdefault(bank_id, {})
        bank_months[target_month] = list(items)

    async def list_months_for_bank(self, bank_id: int) -> list[str]:
        bank_months = self.store.bank_items.get(bank_id, {})
        return sort_month_keys(list(bank_months.keys()))


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


class InMemoryWorkflowStatesRepo:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def get_for_user(self, user_id: int) -> WorkflowState | None:
        raw = self.store.workflow_states.get(user_id)
        if raw is None:
            return None
        return WorkflowState.from_dict(deepcopy(raw))

    async def save_for_user(self, user_id: int, state: WorkflowState) -> None:
        self.store.workflow_states[user_id] = deepcopy(state.to_dict())

    async def delete_for_user(self, user_id: int) -> None:
        self.store.workflow_states.pop(user_id, None)


class InMemoryUnitOfWork(UnitOfWorkPort):
    def __init__(self, store: InMemoryStore) -> None:
        self.users = InMemoryUsersRepo(store)
        self.identities = InMemoryIdentitiesRepo(store)
        self.credentials = InMemoryCredentialsRepo(store)
        self.banks = InMemoryBanksRepo(store)
        self.cashback = InMemoryCashbackRepo(store)
        self.logs = InMemoryLogsRepo(store)
        self.workflow_states = InMemoryWorkflowStatesRepo(store)

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

    async def extract_text(self, upload: ImageUpload) -> str:
        _ = upload
        return self.value


@pytest.fixture()
def dummy_ocr() -> DummyOCR:
    return DummyOCR()
