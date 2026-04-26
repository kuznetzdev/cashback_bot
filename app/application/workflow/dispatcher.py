from __future__ import annotations

from app.application.presenters import workflow_screens
from app.application.presenters.workflow_formatters import target_label
from app.application.workflow import banks, draft, interrupts, navigation, text_intents
from app.application.workflow.dependencies import WorkflowDependencies, log_workflow_event
from app.application.workflow.models import Effect, UserCommand, WorkflowResult, WorkflowState
from app.domain.errors import ValidationError
from app.domain.models import UserAccount


class WorkflowDispatcher:
    def __init__(self, deps: WorkflowDependencies) -> None:
        self.deps = deps

    async def execute(self, user: UserAccount, state: WorkflowState, command: UserCommand) -> WorkflowResult:
        current_user = user
        current_state = state
        current_command = command
        queued_effects: list[Effect] = []

        while True:
            if current_command.name == "continue_draft":
                interrupts.clear_interrupt_target(current_state)
                return self._finalize(
                    workflow_screens.result_with_screen(
                        user=current_user,
                        state=current_state,
                        screen=workflow_screens.preview_screen(
                            current_state, current_user.language, self.deps.categories
                        ),
                    ),
                    queued_effects,
                )

            if current_command.name == "discard_draft_and_go":
                target_command = interrupts.take_interrupt_target(current_state)
                await log_workflow_event(
                    self.deps,
                    current_user.id,
                    "draft_discarded_via_interrupt",
                    {"target": target_command.name},
                )
                queued_effects.append(
                    Effect(
                        kind="show_status",
                        payload={"message_key": "messages.draft_discarded", "transient": True},
                    )
                )
                current_state = WorkflowState()
                current_command = target_command
                continue

            if current_command.name == "save_draft_and_go":
                if not interrupts.can_save_draft(current_state):
                    raise ValidationError("errors.no_items_to_save")
                target_command = interrupts.take_interrupt_target(current_state)
                await draft.save_bank(self.deps, current_user.id, current_state)
                await log_workflow_event(
                    self.deps, current_user.id, "draft_saved_via_interrupt", {"target": target_command.name}
                )
                queued_effects.append(
                    Effect(
                        kind="show_status", payload={"message_key": "messages.saved_bank", "transient": True}
                    )
                )
                current_state = WorkflowState()
                current_command = target_command
                continue

            if interrupts.should_interrupt_navigation(current_state, current_command):
                interrupts.set_interrupt_target(current_state, current_command)
                await log_workflow_event(
                    self.deps, current_user.id, "draft_interrupt_prompt", {"target": current_command.name}
                )
                return self._finalize(
                    workflow_screens.result_with_screen(
                        user=current_user,
                        state=current_state,
                        screen=workflow_screens.interrupt_screen(
                            target_label_key=target_label(
                                interrupts.peek_interrupt_target_name(current_state)
                            ),
                            can_save=interrupts.can_save_draft(current_state),
                        ),
                    ),
                    queued_effects,
                )

            if current_command.name == "submit_text":
                routed = await text_intents.route_text(
                    self.deps, current_user, current_state, str(current_command.payload["text"])
                )
                if isinstance(routed, UserCommand):
                    current_command = routed
                    continue
                return self._finalize(routed, queued_effects)

            if current_command.name == "save_bank":
                bank_id = await draft.save_bank(self.deps, current_user.id, current_state)
                queued_effects.append(
                    Effect(
                        kind="show_status", payload={"message_key": "messages.saved_bank", "transient": True}
                    )
                )
                current_command = UserCommand(name="open_bank", payload={"id": bank_id})
                continue

            result = await draft.handle_command(self.deps, current_user, current_state, current_command)
            if result is None:
                result = await banks.handle_command(self.deps, current_user, current_state, current_command)
            if result is None:
                result = await navigation.handle_command(
                    self.deps, current_user, current_state, current_command
                )
            if result is None:
                raise ValidationError("errors.unknown_command")
            return self._finalize(result, queued_effects)

    @staticmethod
    def _finalize(result: WorkflowResult, queued_effects: list[Effect]) -> WorkflowResult:
        if queued_effects:
            result.effects.extend(queued_effects)
        return result
