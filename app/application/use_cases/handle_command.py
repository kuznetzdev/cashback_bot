from __future__ import annotations

from collections.abc import Callable

from app.application.contracts.ports import OCRPort, UnitOfWorkPort
from app.application.use_cases.best_card_for_category import BestCardForCategoryUseCase
from app.application.use_cases.change_language import ChangeLanguageUseCase
from app.application.use_cases.delete_bank import DeleteBankUseCase
from app.application.use_cases.delete_category import DeleteCategoryUseCase
from app.application.use_cases.get_bank_details import GetBankDetailsUseCase
from app.application.use_cases.get_history import GetHistoryUseCase
from app.application.use_cases.get_ranking import GetRankingUseCase
from app.application.use_cases.get_user_banks import GetUserBanksUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.parse_manual_cashback import ParseManualCashbackUseCase
from app.application.use_cases.process_uploaded_image import ProcessUploadedImageUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.application.use_cases.toggle_notifications import ToggleNotificationsUseCase
from app.application.workflow.dependencies import WorkflowDependencies
from app.application.workflow.dispatcher import WorkflowDispatcher
from app.application.workflow.models import UserCommand, WorkflowResult, WorkflowState
from app.domain.models import UserAccount
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService

POPULAR_BANKS = (
    "T-Bank",
    "Sber",
    "Alfa",
    "VTB",
    "Gazprombank",
    "Raiffeisen",
    "Ozon",
    "Yandex Pay",
)


class HandleCommandUseCase:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        parser: ParserService,
        categories: CategoryService,
        ranking: RankingService,
        ocr: OCRPort,
        parse_manual_use_case: ParseManualCashbackUseCase | None = None,
        process_uploaded_image_use_case: ProcessUploadedImageUseCase | None = None,
        save_bank_draft_use_case: SaveBankDraftUseCase | None = None,
        get_user_banks_use_case: GetUserBanksUseCase | None = None,
        get_bank_details_use_case: GetBankDetailsUseCase | None = None,
        delete_bank_use_case: DeleteBankUseCase | None = None,
        delete_category_use_case: DeleteCategoryUseCase | None = None,
        get_ranking_use_case: GetRankingUseCase | None = None,
        best_card_for_category_use_case: BestCardForCategoryUseCase | None = None,
        get_history_use_case: GetHistoryUseCase | None = None,
        change_language_use_case: ChangeLanguageUseCase | None = None,
        toggle_notifications_use_case: ToggleNotificationsUseCase | None = None,
        log_event_use_case: LogEventUseCase | None = None,
    ) -> None:
        parse_manual = parse_manual_use_case or ParseManualCashbackUseCase(parser)
        process_uploaded_image = process_uploaded_image_use_case or ProcessUploadedImageUseCase(ocr, parser)
        save_bank_draft = save_bank_draft_use_case or SaveBankDraftUseCase(uow_factory)
        get_user_banks = get_user_banks_use_case or GetUserBanksUseCase(uow_factory)
        get_bank_details = get_bank_details_use_case or GetBankDetailsUseCase(uow_factory)
        delete_bank = delete_bank_use_case or DeleteBankUseCase(uow_factory)
        delete_category = delete_category_use_case or DeleteCategoryUseCase(uow_factory, categories)
        get_ranking = get_ranking_use_case or GetRankingUseCase(uow_factory, ranking)
        best_card_for_category = best_card_for_category_use_case or BestCardForCategoryUseCase(
            uow_factory, ranking, categories
        )
        get_history = get_history_use_case or GetHistoryUseCase(uow_factory)
        change_language = change_language_use_case or ChangeLanguageUseCase(uow_factory)
        toggle_notifications = toggle_notifications_use_case or ToggleNotificationsUseCase(uow_factory)
        log_event = log_event_use_case or LogEventUseCase(uow_factory)
        deps = WorkflowDependencies(
            parser=parser,
            categories=categories,
            parse_manual_use_case=parse_manual,
            process_uploaded_image_use_case=process_uploaded_image,
            save_bank_draft_use_case=save_bank_draft,
            get_user_banks_use_case=get_user_banks,
            get_bank_details_use_case=get_bank_details,
            delete_bank_use_case=delete_bank,
            delete_category_use_case=delete_category,
            get_ranking_use_case=get_ranking,
            best_card_for_category_use_case=best_card_for_category,
            get_history_use_case=get_history,
            change_language_use_case=change_language,
            toggle_notifications_use_case=toggle_notifications,
            log_event=lambda user_id, action, payload=None: log_event.execute(
                user_id=user_id,
                action=action,
                payload=payload,
            ),
            popular_banks=POPULAR_BANKS,
        )
        self.dispatcher = WorkflowDispatcher(deps)

    async def execute(self, user: UserAccount, state: WorkflowState, command: UserCommand) -> WorkflowResult:
        return await self.dispatcher.execute(user, state, command)
