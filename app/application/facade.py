from __future__ import annotations

from app.application.models import UserCommand, UserContext, WorkflowResult, WorkflowState
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.domain.models import UserProfile


class ApplicationFacade:
    def __init__(
        self,
        sync_user_use_case: SyncTelegramUserUseCase,
        handle_command_use_case: HandleCommandUseCase,
        reminders_use_case: SendMonthlyRemindersUseCase,
        log_event_use_case: LogEventUseCase,
    ) -> None:
        self.sync_user_use_case = sync_user_use_case
        self.handle_command_use_case = handle_command_use_case
        self.reminders_use_case = reminders_use_case
        self.log_event_use_case = log_event_use_case

    async def sync_user(self, ctx: UserContext, *, log_action: str | None = None) -> UserProfile:
        return await self.sync_user_use_case.execute(ctx, log_action=log_action)

    async def handle_command(self, user: UserProfile, state: WorkflowState, command: UserCommand) -> WorkflowResult:
        return await self.handle_command_use_case.execute(user, state, command)

    async def send_monthly_reminders(self) -> int:
        return await self.reminders_use_case.execute()

    async def log_event(self, *, user_id: int, action: str, payload: dict[str, object] | None = None) -> None:
        await self.log_event_use_case.execute(user_id=user_id, action=action, payload=payload)
