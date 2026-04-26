from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from app.application.contracts.ports import OCRPort, UnitOfWorkPort
from app.application.models import UserContext
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
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.application.use_cases.toggle_notifications import ToggleNotificationsUseCase
from app.application.workflow.dependencies import WorkflowDependencies
from app.application.workflow.models import UserCommand, WorkflowState
from app.application.workflow.text_intents import route_text
from app.domain.models import CashbackDraftItem, UserAccount
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService


def _build_deps(
    uow_factory: Callable[[], UnitOfWorkPort],
    categories: CategoryService,
    parser: ParserService,
    ranking: RankingService,
    dummy_ocr: OCRPort,
) -> WorkflowDependencies:
    log_event = LogEventUseCase(uow_factory)
    return WorkflowDependencies(
        parser=parser,
        categories=categories,
        parse_manual_use_case=ParseManualCashbackUseCase(parser),
        process_uploaded_image_use_case=ProcessUploadedImageUseCase(dummy_ocr, parser),
        save_bank_draft_use_case=SaveBankDraftUseCase(uow_factory),
        get_user_banks_use_case=GetUserBanksUseCase(uow_factory),
        get_bank_details_use_case=GetBankDetailsUseCase(uow_factory),
        delete_bank_use_case=DeleteBankUseCase(uow_factory),
        delete_category_use_case=DeleteCategoryUseCase(uow_factory, categories),
        get_ranking_use_case=GetRankingUseCase(uow_factory, ranking),
        best_card_for_category_use_case=BestCardForCategoryUseCase(uow_factory, ranking, categories),
        get_history_use_case=GetHistoryUseCase(uow_factory),
        change_language_use_case=ChangeLanguageUseCase(uow_factory),
        toggle_notifications_use_case=ToggleNotificationsUseCase(uow_factory),
        log_event=lambda user_id, action, payload=None: log_event.execute(
            user_id=user_id,
            action=action,
            payload=payload,
        ),
        popular_banks=("T-Bank", "Sber"),
    )


async def _create_user(uow_factory: Callable[[], UnitOfWorkPort]) -> UserAccount:
    sync = SyncTelegramUserUseCase(uow_factory, default_language="ru")
    return await sync.execute(
        ctx=UserContext(external_user_id=1001, username="demo", full_name="Demo User"),
        log_action="user_started",
    )


async def test_pending_input_routes_to_expected_command(uow_factory, dummy_ocr) -> None:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    deps = _build_deps(uow_factory, categories, parser, ranking, dummy_ocr)
    user = await _create_user(uow_factory)

    command = await route_text(deps, user, WorkflowState(pending_input_kind="manual_lines"), "Fuel 5%")

    assert isinstance(command, UserCommand)
    assert command.name == "submit_manual_text"
    assert command.payload["text"] == "Fuel 5%"


async def test_best_query_routes_to_top_category(uow_factory, dummy_ocr) -> None:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    deps = _build_deps(uow_factory, categories, parser, ranking, dummy_ocr)
    user = await _create_user(uow_factory)
    expected_slug = categories.normalize("fuel").slug

    command = await route_text(deps, user, WorkflowState(), "best cashback for fuel")

    assert isinstance(command, UserCommand)
    assert command.name == "open_top_category"
    assert command.payload["slug"] == expected_slug


async def test_delete_bank_text_intent_deletes_bank_and_returns_home(uow_factory, dummy_ocr, store) -> None:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    deps = _build_deps(uow_factory, categories, parser, ranking, dummy_ocr)
    user = await _create_user(uow_factory)
    await deps.save_bank_draft_use_case.execute(
        user_id=user.id,
        bank_id=None,
        bank_name="T-Bank",
        items=[
            CashbackDraftItem(
                raw_category="Fuel", normalized_category="fuel", percent=Decimal("5"), source_type="manual"
            )
        ],
    )

    result = await route_text(deps, user, WorkflowState(), "delete bank T-Bank")

    assert result.screen.id == "home"
    assert result.screen.body_key == "messages.deleted_bank"
    assert store.banks == {}


async def test_delete_category_text_intent_returns_summary_screen(uow_factory, dummy_ocr, store) -> None:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    deps = _build_deps(uow_factory, categories, parser, ranking, dummy_ocr)
    user = await _create_user(uow_factory)
    await deps.save_bank_draft_use_case.execute(
        user_id=user.id,
        bank_id=None,
        bank_name="T-Bank",
        items=[
            CashbackDraftItem(
                raw_category="Fuel",
                normalized_category=categories.normalize("Fuel").slug,
                percent=Decimal("5"),
                source_type="manual",
            )
        ],
    )

    result = await route_text(deps, user, WorkflowState(), "delete category fuel")

    assert result.screen.id == "delete_category_result"
    assert result.screen.body_params == {"count": 1, "banks": 1}
    assert list(store.bank_items.values()) == [[]]


async def test_unknown_text_returns_help_with_status_effect(uow_factory, dummy_ocr) -> None:
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    deps = _build_deps(uow_factory, categories, parser, ranking, dummy_ocr)
    user = await _create_user(uow_factory)

    result = await route_text(deps, user, WorkflowState(), "abracadabra")

    assert result.screen.id == "help"
    assert any(
        effect.kind == "show_status" and effect.payload["message_key"] == "errors.unknown_command"
        for effect in result.effects
    )
