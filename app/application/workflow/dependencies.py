from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.application.use_cases.best_card_for_category import BestCardForCategoryUseCase
from app.application.use_cases.change_language import ChangeLanguageUseCase
from app.application.use_cases.delete_bank import DeleteBankUseCase
from app.application.use_cases.delete_category import DeleteCategoryUseCase
from app.application.use_cases.get_bank_details import GetBankDetailsUseCase
from app.application.use_cases.get_history import GetHistoryUseCase
from app.application.use_cases.get_ranking import GetRankingUseCase
from app.application.use_cases.get_user_banks import GetUserBanksUseCase
from app.application.use_cases.parse_manual_cashback import ParseManualCashbackUseCase
from app.application.use_cases.process_uploaded_image import ProcessUploadedImageUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.application.use_cases.toggle_notifications import ToggleNotificationsUseCase
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService

logger = logging.getLogger(__name__)

WorkflowLogEvent = Callable[[int, str, dict[str, object] | None], Awaitable[None]]


@dataclass(slots=True)
class WorkflowDependencies:
    parser: ParserService
    categories: CategoryService
    parse_manual_use_case: ParseManualCashbackUseCase
    process_uploaded_image_use_case: ProcessUploadedImageUseCase
    save_bank_draft_use_case: SaveBankDraftUseCase
    get_user_banks_use_case: GetUserBanksUseCase
    get_bank_details_use_case: GetBankDetailsUseCase
    delete_bank_use_case: DeleteBankUseCase
    delete_category_use_case: DeleteCategoryUseCase
    get_ranking_use_case: GetRankingUseCase
    best_card_for_category_use_case: BestCardForCategoryUseCase
    get_history_use_case: GetHistoryUseCase
    change_language_use_case: ChangeLanguageUseCase
    toggle_notifications_use_case: ToggleNotificationsUseCase
    log_event: WorkflowLogEvent
    popular_banks: tuple[str, ...]


async def log_workflow_event(
    deps: WorkflowDependencies,
    user_id: int,
    action: str,
    payload: dict[str, object] | None = None,
) -> None:
    try:
        await deps.log_event(user_id, action, payload)
    except (RuntimeError, OSError) as error:
        logger.warning("Non-blocking workflow log failure for action %s: %s", action, error)
    except Exception as error:
        logger.warning("Non-blocking unexpected workflow log failure for action %s: %s", action, error)
