from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.application.models import UserContext
from app.domain.models import UserProfile


class SyncTelegramUserUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], default_language: str) -> None:
        self.uow_factory = uow_factory
        self.default_language = default_language

    async def execute(self, ctx: UserContext, *, log_action: str | None = None) -> UserProfile:
        async with self.uow_factory() as uow:
            user = await uow.users.upsert(
                external_user_id=ctx.external_user_id,
                username=ctx.username,
                full_name=ctx.full_name,
                default_language=self.default_language,
            )
            if log_action:
                await uow.logs.add(user.id, log_action, {"external_user_id": user.external_user_id})
            await uow.commit()
            return user
