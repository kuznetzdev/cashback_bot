from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.errors import NotFoundError, ValidationError
from app.domain.models import UserProfile


class ChangeLanguageUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, language: str) -> UserProfile:
        if language not in {"ru", "en"}:
            raise ValidationError("errors.invalid_language")
        async with self.uow_factory() as uow:
            await uow.users.set_language(user_id, language)
            await uow.logs.add(user_id, "language_changed", {"language": language})
            user = await uow.users.get_by_id(user_id)
            await uow.commit()
        if user is None:
            raise NotFoundError("errors.unexpected")
        return user
