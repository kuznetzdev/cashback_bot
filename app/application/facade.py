from __future__ import annotations

from app.application.auth.models import ExternalIdentityContext, LocalAuthenticationCommand, LocalRegistrationCommand
from app.application.auth.use_cases import (
    AuthenticateExternalIdentityUseCase,
    AuthenticateLocalUserUseCase,
    GetUserAccountUseCase,
    LinkExternalIdentityUseCase,
    ListExternalIdentitiesUseCase,
    RegisterLocalUserUseCase,
    UnlinkExternalIdentityUseCase,
)
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.get_workflow_state import GetWorkflowStateUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.save_workflow_state import SaveWorkflowStateUseCase
from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.application.workflow.models import UserCommand, WorkflowResult, WorkflowState
from app.domain.models import UserAccount, UserIdentity


class ApplicationFacade:
    def __init__(
        self,
        register_local_user_use_case: RegisterLocalUserUseCase,
        authenticate_local_user_use_case: AuthenticateLocalUserUseCase,
        authenticate_external_identity_use_case: AuthenticateExternalIdentityUseCase,
        link_external_identity_use_case: LinkExternalIdentityUseCase,
        unlink_external_identity_use_case: UnlinkExternalIdentityUseCase,
        get_user_account_use_case: GetUserAccountUseCase,
        list_external_identities_use_case: ListExternalIdentitiesUseCase,
        handle_command_use_case: HandleCommandUseCase,
        get_workflow_state_use_case: GetWorkflowStateUseCase,
        save_workflow_state_use_case: SaveWorkflowStateUseCase,
        reminders_use_case: SendMonthlyRemindersUseCase,
        log_event_use_case: LogEventUseCase,
    ) -> None:
        self.register_local_user_use_case = register_local_user_use_case
        self.authenticate_local_user_use_case = authenticate_local_user_use_case
        self.authenticate_external_identity_use_case = authenticate_external_identity_use_case
        self.link_external_identity_use_case = link_external_identity_use_case
        self.unlink_external_identity_use_case = unlink_external_identity_use_case
        self.get_user_account_use_case = get_user_account_use_case
        self.list_external_identities_use_case = list_external_identities_use_case
        self.handle_command_use_case = handle_command_use_case
        self.get_workflow_state_use_case = get_workflow_state_use_case
        self.save_workflow_state_use_case = save_workflow_state_use_case
        self.reminders_use_case = reminders_use_case
        self.log_event_use_case = log_event_use_case

    async def register_local_user(self, command: LocalRegistrationCommand) -> UserAccount:
        return await self.register_local_user_use_case.execute(command)

    async def authenticate_local_user(self, command: LocalAuthenticationCommand) -> UserAccount:
        return await self.authenticate_local_user_use_case.execute(command)

    async def authenticate_external_identity(
        self,
        identity: ExternalIdentityContext,
        *,
        create_user_if_missing: bool,
        log_action: str | None = None,
    ) -> UserAccount:
        return await self.authenticate_external_identity_use_case.execute(
            identity,
            create_user_if_missing=create_user_if_missing,
            log_action=log_action,
        )

    async def link_external_identity(self, *, user_id: int, identity: ExternalIdentityContext) -> UserIdentity:
        return await self.link_external_identity_use_case.execute(user_id=user_id, identity=identity)

    async def unlink_external_identity(self, *, user_id: int, provider: str) -> None:
        await self.unlink_external_identity_use_case.execute(user_id=user_id, provider=provider)

    async def get_user(self, user_id: int) -> UserAccount | None:
        return await self.get_user_account_use_case.execute(user_id=user_id)

    async def list_external_identities(self, *, user_id: int) -> list[UserIdentity]:
        return await self.list_external_identities_use_case.execute(user_id=user_id)

    async def handle_command(self, user: UserAccount, state: WorkflowState, command: UserCommand) -> WorkflowResult:
        return await self.handle_command_use_case.execute(user, state, command)

    async def resume_workflow(self, user: UserAccount, state: WorkflowState) -> WorkflowResult:
        return await self.handle_command_use_case.resume(user, state)

    async def get_workflow_state(self, *, user_id: int) -> WorkflowState:
        return await self.get_workflow_state_use_case.execute(user_id)

    async def save_workflow_state(self, *, user_id: int, state: WorkflowState) -> None:
        await self.save_workflow_state_use_case.execute(user_id=user_id, state=state)

    async def send_monthly_reminders(self) -> int:
        return await self.reminders_use_case.execute()

    async def log_event(self, *, user_id: int, action: str, payload: dict[str, object] | None = None) -> None:
        await self.log_event_use_case.execute(user_id=user_id, action=action, payload=payload)
