from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.contracts.ports import UnitOfWorkPort
from app.adapters.postgres.repositories import (
    PostgresBankRepository,
    PostgresCashbackRepository,
    PostgresLocalCredentialsRepository,
    PostgresLogRepository,
    PostgresUserIdentityRepository,
    PostgresUserRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWorkPort):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.users: PostgresUserRepository
        self.identities: PostgresUserIdentityRepository
        self.credentials: PostgresLocalCredentialsRepository
        self.banks: PostgresBankRepository
        self.cashback: PostgresCashbackRepository
        self.logs: PostgresLogRepository

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.users = PostgresUserRepository(self.session)
        self.identities = PostgresUserIdentityRepository(self.session)
        self.credentials = PostgresLocalCredentialsRepository(self.session)
        self.banks = PostgresBankRepository(self.session)
        self.cashback = PostgresCashbackRepository(self.session)
        self.logs = PostgresLogRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.session is None:
            return
        if exc:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()


def build_uow_factory(session_factory: async_sessionmaker[AsyncSession]) -> Callable[[], SqlAlchemyUnitOfWork]:
    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory
