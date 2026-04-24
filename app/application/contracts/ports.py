from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.application.dto.media import ImageUpload
from app.application.workflow.models import WorkflowState
from app.domain.models import Bank, CashbackDraftItem, DeliveryTarget, LocalCredentials, UserAccount, UserIdentity, UserLogEntry
from app.domain.services.ranking import RankingEntry


class UserRepositoryPort(Protocol):
    async def create(self, *, display_name: str, default_language: str) -> UserAccount:
        ...

    async def get_by_id(self, user_id: int) -> UserAccount | None:
        ...

    async def set_language(self, user_id: int, language: str) -> None:
        ...

    async def toggle_notifications(self, user_id: int) -> bool:
        ...

    async def list_notification_enabled(self) -> list[UserAccount]:
        ...


class UserIdentityRepositoryPort(Protocol):
    async def get_by_provider_identity(self, *, provider: str, provider_user_id: str) -> UserIdentity | None:
        ...

    async def list_for_user(self, user_id: int) -> list[UserIdentity]:
        ...

    async def count_for_user(self, user_id: int) -> int:
        ...

    async def upsert_for_user(
        self,
        *,
        user_id: int,
        provider: str,
        provider_user_id: str,
        provider_username: str | None,
        provider_display_name: str | None,
    ) -> UserIdentity:
        ...

    async def remove_for_user(self, *, user_id: int, provider: str) -> bool:
        ...

    async def list_delivery_targets(self, *, provider: str) -> list[DeliveryTarget]:
        ...


class LocalCredentialsRepositoryPort(Protocol):
    async def create(
        self,
        *,
        user_id: int,
        username: str,
        email: str | None,
        password_hash: str,
    ) -> LocalCredentials:
        ...

    async def get_by_username(self, username: str) -> LocalCredentials | None:
        ...

    async def get_by_email(self, email: str) -> LocalCredentials | None:
        ...

    async def get_by_user_id(self, user_id: int) -> LocalCredentials | None:
        ...

    async def has_for_user(self, user_id: int) -> bool:
        ...


class BankRepositoryPort(Protocol):
    async def list_for_user(self, user_id: int) -> list[Bank]:
        ...

    async def get_for_user(self, user_id: int, bank_id: int) -> Bank | None:
        ...

    async def get_by_name(self, user_id: int, bank_name: str) -> Bank | None:
        ...

    async def create(self, user_id: int, bank_name: str) -> Bank:
        ...

    async def update_name(self, bank_id: int, bank_name: str) -> None:
        ...

    async def delete(self, bank_id: int) -> None:
        ...


class CashbackRepositoryPort(Protocol):
    async def list_for_bank(self, bank_id: int, target_month: str | None = None) -> list[CashbackDraftItem]:
        ...

    async def replace_for_bank(self, bank_id: int, target_month: str, items: list[CashbackDraftItem]) -> None:
        ...

    async def list_months_for_bank(self, bank_id: int) -> list[str]:
        ...


class LogRepositoryPort(Protocol):
    async def add(self, user_id: int, action: str, payload: dict | None = None) -> None:
        ...

    async def list_recent(self, user_id: int, limit: int) -> list[UserLogEntry]:
        ...

    async def list_action_since(self, user_id: int, action: str, since: datetime) -> list[UserLogEntry]:
        ...


class WorkflowStateRepositoryPort(Protocol):
    async def get_for_user(self, user_id: int) -> WorkflowState | None:
        ...

    async def save_for_user(self, user_id: int, state: WorkflowState) -> None:
        ...

    async def delete_for_user(self, user_id: int) -> None:
        ...


class UnitOfWorkPort(Protocol):
    users: UserRepositoryPort
    identities: UserIdentityRepositoryPort
    credentials: LocalCredentialsRepositoryPort
    banks: BankRepositoryPort
    cashback: CashbackRepositoryPort
    logs: LogRepositoryPort
    workflow_states: WorkflowStateRepositoryPort

    async def __aenter__(self) -> "UnitOfWorkPort":
        ...

    async def __aexit__(self, exc_type, exc, tb) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...


class OCRPort(Protocol):
    async def extract_text(self, upload: ImageUpload) -> str:
        ...


class ReminderSenderPort(Protocol):
    async def send_monthly_reminder(self, target: DeliveryTarget) -> None:
        ...


class ClockPort(Protocol):
    def now(self) -> datetime:
        ...


class RankingReaderPort(Protocol):
    async def list_entries_for_user(self, user_id: int) -> list[RankingEntry]:
        ...
