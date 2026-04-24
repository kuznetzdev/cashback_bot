from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.application.workflow.models import WorkflowState


class SaveWorkflowStateUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, state: WorkflowState) -> None:
        async with self.uow_factory() as uow:
            if state.is_empty():
                await uow.workflow_states.delete_for_user(user_id)
            else:
                await uow.workflow_states.save_for_user(user_id, state)
            await uow.commit()
