from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import UnitOfWorkPort
from app.application.workflow.models import WorkflowState


class GetWorkflowStateUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, user_id: int) -> WorkflowState:
        async with self.uow_factory() as uow:
            state = await uow.workflow_states.get_for_user(user_id)
            return state if state is not None else WorkflowState()
