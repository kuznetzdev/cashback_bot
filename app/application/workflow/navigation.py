from __future__ import annotations

from app.application.presenters import workflow_screens
from app.application.workflow.dependencies import WorkflowDependencies
from app.application.workflow.models import UserCommand, WorkflowResult, WorkflowState
from app.domain.models import UserAccount


async def handle_command(
    deps: WorkflowDependencies,
    user: UserAccount,
    state: WorkflowState,
    command: UserCommand,
) -> WorkflowResult | None:
    name = command.name
    if name in {"start", "open_home"}:
        return workflow_screens.result_with_screen(
            user=user, state=WorkflowState(), screen=workflow_screens.home_screen()
        )
    if name == "open_help":
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.help_screen()
        )
    if name == "cancel_flow":
        return workflow_screens.result_with_screen(
            user=user, state=WorkflowState(), screen=workflow_screens.home_screen()
        )
    if name == "open_top":
        leaders = await deps.get_ranking_use_case.top_by_category(user.id, user.language)
        global_rating = await deps.get_ranking_use_case.top_global(user.id, user.language) if leaders else []
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.top_screen(leaders, global_rating)
        )
    if name == "open_top_category":
        slug = str(command.payload["slug"])
        # Route through BestCardForCategoryUseCase so related-slug expansion
        # (supermarkets ↔ groceries) matches the inline / slash-command path.
        result = await deps.best_card_for_category_use_case.execute(
            user_id=user.id, query=slug, language=user.language
        )
        return workflow_screens.result_with_screen(
            user=user,
            state=state,
            screen=workflow_screens.top_category_screen(result.leader),
        )
    if name == "open_settings":
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.settings_screen(user)
        )
    if name == "set_language":
        updated_user = await deps.change_language_use_case.execute(
            user_id=user.id, language=str(command.payload["code"])
        )
        return workflow_screens.result_with_screen(
            user=updated_user, state=state, screen=workflow_screens.settings_screen(updated_user)
        )
    if name == "toggle_notifications":
        updated_user = await deps.toggle_notifications_use_case.execute(user_id=user.id)
        return workflow_screens.result_with_screen(
            user=updated_user, state=state, screen=workflow_screens.settings_screen(updated_user)
        )
    if name == "open_history":
        logs = await deps.get_history_use_case.execute(user_id=user.id)
        return workflow_screens.result_with_screen(
            user=user, state=state, screen=workflow_screens.history_screen(logs)
        )
    return None
