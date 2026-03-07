from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Bank, CashbackDraftItem, UserLogEntry, UserProfile
from app.adapters.postgres.models import BankModel, CashbackItemModel, UserLogModel, UserModel, utcnow


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, *, external_user_id: int, username: str | None, full_name: str | None, default_language: str) -> UserProfile:
        user = await self._find_by_external_id(external_user_id)
        if user is None:
            model = UserModel(
                telegram_user_id=external_user_id,
                username=username,
                full_name=full_name,
                language=default_language,
                notifications_enabled=True,
            )
            self.session.add(model)
            await self.session.flush()
            return self._to_domain(model)
        user.username = username
        user.full_name = full_name
        user.updated_at = utcnow()
        await self.session.flush()
        return self._to_domain(user)

    async def get_by_external_id(self, external_user_id: int) -> UserProfile | None:
        model = await self._find_by_external_id(external_user_id)
        return self._to_domain(model) if model else None

    async def get_by_id(self, user_id: int) -> UserProfile | None:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def set_language(self, user_id: int, language: str) -> None:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        model = result.scalar_one_or_none()
        if model:
            model.language = language
            model.updated_at = utcnow()
            await self.session.flush()

    async def toggle_notifications(self, user_id: int) -> bool:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.notifications_enabled = not model.notifications_enabled
        model.updated_at = utcnow()
        await self.session.flush()
        return model.notifications_enabled

    async def list_notification_enabled(self) -> list[UserProfile]:
        result = await self.session.execute(select(UserModel).where(UserModel.notifications_enabled.is_(True)))
        return [self._to_domain(item) for item in result.scalars().all()]

    async def _find_by_external_id(self, external_user_id: int) -> UserModel | None:
        result = await self.session.execute(select(UserModel).where(UserModel.telegram_user_id == external_user_id))
        return result.scalar_one_or_none()

    @staticmethod
    def _to_domain(model: UserModel) -> UserProfile:
        return UserProfile(
            id=model.id,
            external_user_id=model.telegram_user_id,
            username=model.username,
            full_name=model.full_name,
            language=model.language,
            notifications_enabled=model.notifications_enabled,
        )


class PostgresBankRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: int) -> list[Bank]:
        result = await self.session.execute(
            select(BankModel).where(BankModel.user_id == user_id).order_by(func.lower(BankModel.bank_name))
        )
        return [self._to_domain(item) for item in result.scalars().all()]

    async def get_for_user(self, user_id: int, bank_id: int) -> Bank | None:
        result = await self.session.execute(select(BankModel).where(BankModel.user_id == user_id, BankModel.id == bank_id))
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_name(self, user_id: int, bank_name: str) -> Bank | None:
        result = await self.session.execute(
            select(BankModel).where(BankModel.user_id == user_id, func.lower(BankModel.bank_name) == bank_name.strip().lower())
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, user_id: int, bank_name: str) -> Bank:
        model = BankModel(user_id=user_id, bank_name=bank_name.strip())
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def update_name(self, bank_id: int, bank_name: str) -> None:
        result = await self.session.execute(select(BankModel).where(BankModel.id == bank_id))
        model = result.scalar_one_or_none()
        if model:
            model.bank_name = bank_name.strip()
            model.updated_at = utcnow()
            await self.session.flush()

    async def delete(self, bank_id: int) -> None:
        await self.session.execute(delete(BankModel).where(BankModel.id == bank_id))
        await self.session.flush()

    @staticmethod
    def _to_domain(model: BankModel) -> Bank:
        return Bank(id=model.id, user_id=model.user_id, bank_name=model.bank_name)


class PostgresCashbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_bank(self, bank_id: int) -> list[CashbackDraftItem]:
        result = await self.session.execute(
            select(CashbackItemModel)
            .where(CashbackItemModel.bank_id == bank_id)
            .order_by(CashbackItemModel.percent.desc(), CashbackItemModel.normalized_category.asc())
        )
        return [
            CashbackDraftItem(
                raw_category=item.raw_category,
                normalized_category=item.normalized_category,
                percent=item.percent,
                source_type=item.source_type,
            )
            for item in result.scalars().all()
        ]

    async def replace_for_bank(self, bank_id: int, items: list[CashbackDraftItem]) -> None:
        await self.session.execute(delete(CashbackItemModel).where(CashbackItemModel.bank_id == bank_id))
        for item in items:
            self.session.add(
                CashbackItemModel(
                    bank_id=bank_id,
                    raw_category=item.raw_category,
                    normalized_category=item.normalized_category,
                    percent=item.percent,
                    source_type=item.source_type,
                )
            )
        await self.session.flush()


class PostgresLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user_id: int, action: str, payload: dict | None = None) -> None:
        self.session.add(UserLogModel(user_id=user_id, action=action, payload_json=payload))
        await self.session.flush()

    async def list_recent(self, user_id: int, limit: int) -> list[UserLogEntry]:
        result = await self.session.execute(
            select(UserLogModel)
            .where(UserLogModel.user_id == user_id)
            .order_by(desc(UserLogModel.created_at))
            .limit(limit)
        )
        return [self._to_domain(item) for item in result.scalars().all()]

    async def list_action_since(self, user_id: int, action: str, since: datetime) -> list[UserLogEntry]:
        result = await self.session.execute(
            select(UserLogModel)
            .where(UserLogModel.user_id == user_id, UserLogModel.action == action, UserLogModel.created_at >= since)
            .order_by(desc(UserLogModel.created_at))
        )
        return [self._to_domain(item) for item in result.scalars().all()]

    @staticmethod
    def _to_domain(model: UserLogModel) -> UserLogEntry:
        return UserLogEntry(
            id=model.id,
            user_id=model.user_id,
            action=model.action,
            payload=model.payload_json,
            created_at=model.created_at,
        )
