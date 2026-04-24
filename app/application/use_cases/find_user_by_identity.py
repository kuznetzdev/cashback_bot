from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.models import UserAccount


class FindUserByExternalIdentityUseCase:
    """Read-only lookup used by stateless entry points such as Telegram inline
    mode, where triggering user creation for every drive-by query would
    silently register accounts for people who only typed the bot's @-handle."""

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, provider: str, provider_user_id: str) -> UserAccount | None:
        async with self.uow_factory() as uow:
            identity = await uow.identities.get_by_provider_identity(
                provider=provider,
                provider_user_id=provider_user_id,
            )
            if identity is None:
                return None
            return await uow.users.get_by_id(identity.user_id)
