from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.postgres.models import (
    BankModel,
    CashbackItemModel,
    LocalCredentialsModel,
    UserIdentityModel,
    UserLogModel,
    UserModel,
    WorkflowStateModel,
    utcnow,
)
from app.application.months import current_month_key, normalize_month_key, sort_month_keys
from app.application.workflow.models import WorkflowState
from app.domain.models import Bank, CashbackDraftItem, DeliveryTarget, LocalCredentials, UserAccount, UserIdentity, UserLogEntry


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, display_name: str, default_language: str) -> UserAccount:
        model = UserModel(
            display_name=display_name.strip(),
            language=default_language,
            notifications_enabled=True,
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def get_by_id(self, user_id: int) -> UserAccount | None:
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

    async def list_notification_enabled(self) -> list[UserAccount]:
        result = await self.session.execute(select(UserModel).where(UserModel.notifications_enabled.is_(True)))
        return [self._to_domain(item) for item in result.scalars().all()]

    @staticmethod
    def _to_domain(model: UserModel) -> UserAccount:
        return UserAccount(
            id=model.id,
            display_name=model.display_name,
            language=model.language,
            notifications_enabled=model.notifications_enabled,
        )


class PostgresUserIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider_identity(self, *, provider: str, provider_user_id: str) -> UserIdentity | None:
        result = await self.session.execute(
            select(UserIdentityModel).where(
                UserIdentityModel.provider == provider,
                UserIdentityModel.provider_user_id == provider_user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_for_user(self, user_id: int) -> list[UserIdentity]:
        result = await self.session.execute(
            select(UserIdentityModel)
            .where(UserIdentityModel.user_id == user_id)
            .order_by(UserIdentityModel.provider.asc())
        )
        return [self._to_domain(item) for item in result.scalars().all()]

    async def count_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(UserIdentityModel.id)).where(UserIdentityModel.user_id == user_id)
        )
        return int(result.scalar_one())

    async def upsert_for_user(
        self,
        *,
        user_id: int,
        provider: str,
        provider_user_id: str,
        provider_username: str | None,
        provider_display_name: str | None,
    ) -> UserIdentity:
        result = await self.session.execute(
            select(UserIdentityModel).where(
                UserIdentityModel.user_id == user_id,
                UserIdentityModel.provider == provider,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            model = UserIdentityModel(
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_username=provider_username,
                provider_display_name=provider_display_name,
            )
            self.session.add(model)
        else:
            model.provider_user_id = provider_user_id
            model.provider_username = provider_username
            model.provider_display_name = provider_display_name
            model.updated_at = utcnow()

        await self.session.flush()
        return self._to_domain(model)

    async def remove_for_user(self, *, user_id: int, provider: str) -> bool:
        result = await self.session.execute(
            select(UserIdentityModel).where(
                UserIdentityModel.user_id == user_id,
                UserIdentityModel.provider == provider,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self.session.delete(model)
        await self.session.flush()
        return True

    async def list_delivery_targets(self, *, provider: str) -> list[DeliveryTarget]:
        result = await self.session.execute(
            select(UserIdentityModel, UserModel)
            .join(UserModel, UserModel.id == UserIdentityModel.user_id)
            .where(
                UserIdentityModel.provider == provider,
                UserModel.notifications_enabled.is_(True),
            )
            .order_by(UserIdentityModel.user_id.asc())
        )
        targets: list[DeliveryTarget] = []
        for identity_model, user_model in result.all():
            targets.append(
                DeliveryTarget(
                    user_id=user_model.id,
                    provider=identity_model.provider,
                    destination=identity_model.provider_user_id,
                    language=user_model.language,
                )
            )
        return targets

    @staticmethod
    def _to_domain(model: UserIdentityModel) -> UserIdentity:
        return UserIdentity(
            id=model.id,
            user_id=model.user_id,
            provider=model.provider,
            provider_user_id=model.provider_user_id,
            provider_username=model.provider_username,
            provider_display_name=model.provider_display_name,
        )


class PostgresLocalCredentialsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        username: str,
        email: str | None,
        password_hash: str,
    ) -> LocalCredentials:
        model = LocalCredentialsModel(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def get_by_username(self, username: str) -> LocalCredentials | None:
        result = await self.session.execute(
            select(LocalCredentialsModel).where(LocalCredentialsModel.username == username)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_email(self, email: str) -> LocalCredentials | None:
        result = await self.session.execute(
            select(LocalCredentialsModel).where(LocalCredentialsModel.email == email)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_user_id(self, user_id: int) -> LocalCredentials | None:
        result = await self.session.execute(
            select(LocalCredentialsModel).where(LocalCredentialsModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def has_for_user(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(LocalCredentialsModel.id).where(LocalCredentialsModel.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _to_domain(model: LocalCredentialsModel) -> LocalCredentials:
        return LocalCredentials(
            id=model.id,
            user_id=model.user_id,
            username=model.username,
            email=model.email,
            password_hash=model.password_hash,
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

    async def list_for_bank(self, bank_id: int, target_month: str | None = None) -> list[CashbackDraftItem]:
        month = normalize_month_key(target_month) if target_month is not None else current_month_key()
        result = await self.session.execute(
            select(CashbackItemModel)
            .where(
                CashbackItemModel.bank_id == bank_id,
                CashbackItemModel.target_month == month,
            )
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

    async def replace_for_bank(self, bank_id: int, target_month: str, items: list[CashbackDraftItem]) -> None:
        month = normalize_month_key(target_month)
        await self.session.execute(
            delete(CashbackItemModel).where(
                CashbackItemModel.bank_id == bank_id,
                CashbackItemModel.target_month == month,
            )
        )
        for item in items:
            self.session.add(
                CashbackItemModel(
                    bank_id=bank_id,
                    target_month=month,
                    raw_category=item.raw_category,
                    normalized_category=item.normalized_category,
                    percent=item.percent,
                    source_type=item.source_type,
                )
            )
        await self.session.flush()

    async def list_months_for_bank(self, bank_id: int) -> list[str]:
        result = await self.session.execute(
            select(CashbackItemModel.target_month)
            .where(CashbackItemModel.bank_id == bank_id)
            .distinct()
            .order_by(CashbackItemModel.target_month.asc())
        )
        return sort_month_keys([str(month) for month in result.scalars().all()])


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


class PostgresWorkflowStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_user(self, user_id: int) -> WorkflowState | None:
        result = await self.session.execute(select(WorkflowStateModel).where(WorkflowStateModel.user_id == user_id))
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return WorkflowState.from_dict(model.state_json)

    async def save_for_user(self, user_id: int, state: WorkflowState) -> None:
        result = await self.session.execute(select(WorkflowStateModel).where(WorkflowStateModel.user_id == user_id))
        model = result.scalar_one_or_none()
        serialized = state.to_dict()
        if model is None:
            model = WorkflowStateModel(user_id=user_id, state_json=serialized)
            self.session.add(model)
        else:
            model.state_json = serialized
            model.updated_at = utcnow()
        await self.session.flush()

    async def delete_for_user(self, user_id: int) -> None:
        await self.session.execute(delete(WorkflowStateModel).where(WorkflowStateModel.user_id == user_id))
        await self.session.flush()
