from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.domain.errors import NotFoundError
from app.domain.models import UserProfile


class ToggleNotificationsUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int) -> UserProfile:
        async with self.uow_factory() as uow:
            enabled = await uow.users.toggle_notifications(user_id)
            await uow.logs.add(user_id, "notifications_toggled", {"notifications_enabled": enabled})
            user = await uow.users.get_by_id(user_id)
            await uow.commit()
        if user is None:
            raise NotFoundError("errors.unexpected")
        return user
