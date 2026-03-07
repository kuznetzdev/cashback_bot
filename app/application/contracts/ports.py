from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.domain.models import Bank, CashbackDraftItem, UserLogEntry, UserProfile
from app.domain.services.ranking import RankingEntry


class UserRepositoryPort(Protocol):
    async def upsert(
        self,
        *,
        external_user_id: int,
        username: str | None,
        full_name: str | None,
        default_language: str,
    ) -> UserProfile:
        ...

    async def get_by_external_id(self, external_user_id: int) -> UserProfile | None:
        ...

    async def get_by_id(self, user_id: int) -> UserProfile | None:
        ...

    async def set_language(self, user_id: int, language: str) -> None:
        ...

    async def toggle_notifications(self, user_id: int) -> bool:
        ...

    async def list_notification_enabled(self) -> list[UserProfile]:
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
    async def list_for_bank(self, bank_id: int) -> list[CashbackDraftItem]:
        ...

    async def replace_for_bank(self, bank_id: int, items: list[CashbackDraftItem]) -> None:
        ...


class LogRepositoryPort(Protocol):
    async def add(self, user_id: int, action: str, payload: dict | None = None) -> None:
        ...

    async def list_recent(self, user_id: int, limit: int) -> list[UserLogEntry]:
        ...

    async def list_action_since(self, user_id: int, action: str, since: datetime) -> list[UserLogEntry]:
        ...


class UnitOfWorkPort(Protocol):
    users: UserRepositoryPort
    banks: BankRepositoryPort
    cashback: CashbackRepositoryPort
    logs: LogRepositoryPort

    async def __aenter__(self) -> "UnitOfWorkPort":
        ...

    async def __aexit__(self, exc_type, exc, tb) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...


class OCRPort(Protocol):
    async def extract_text(self, image_path: Path) -> str:
        ...


class BinarySourcePort(Protocol):
    async def save_photo_to_temp(self, source: object) -> Path:
        ...

    async def remove_temp_file(self, path: Path) -> None:
        ...


class ReminderSenderPort(Protocol):
    async def send_monthly_reminder(self, user: UserProfile) -> None:
        ...


class ClockPort(Protocol):
    def now(self) -> datetime:
        ...


class RankingReaderPort(Protocol):
    async def list_entries_for_user(self, user_id: int) -> list[RankingEntry]:
        ...
