from __future__ import annotations

from collections.abc import Callable

from app.application.auth.models import ExternalIdentityContext
from app.application.auth.use_cases import AuthenticateExternalIdentityUseCase
from app.application.contracts.ports import UnitOfWorkPort
from app.application.models import UserContext
from app.domain.models import UserAccount


class SyncTelegramUserUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], default_language: str) -> None:
        self.auth_use_case = AuthenticateExternalIdentityUseCase(
            uow_factory, default_language=default_language
        )

    async def execute(self, ctx: UserContext, *, log_action: str | None = None) -> UserAccount:
        identity = ExternalIdentityContext(
            provider="telegram",
            provider_user_id=str(ctx.external_user_id),
            provider_username=ctx.username,
            provider_display_name=ctx.full_name,
        )
        return await self.auth_use_case.execute(identity, create_user_if_missing=True, log_action=log_action)
