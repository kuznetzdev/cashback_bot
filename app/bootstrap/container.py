from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import logging

from app.adapters.auth_local import Argon2PasswordHasher
from app.adapters.ocr_openai_vision import OpenAIVisionOCRAdapter
from app.adapters.ocr_tesseract import TesseractOCRAdapter
from app.adapters.postgres.session import create_session_factory
from app.adapters.postgres.uow import SqlAlchemyUnitOfWork, build_uow_factory
from app.adapters.system import SystemClock
from app.application import ApplicationFacade
from app.application.auth.use_cases import (
    AuthenticateExternalIdentityUseCase,
    AuthenticateLocalUserUseCase,
    GetUserAccountUseCase,
    LinkExternalIdentityUseCase,
    ListExternalIdentitiesUseCase,
    RegisterLocalUserUseCase,
    UnlinkExternalIdentityUseCase,
)
from app.application.contracts.ports import ReminderSenderPort
from app.application.use_cases.best_card_for_category import BestCardForCategoryUseCase
from app.application.use_cases.find_user_by_identity import FindUserByExternalIdentityUseCase
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.get_bank_details import GetBankDetailsUseCase
from app.application.use_cases.get_history import GetHistoryUseCase
from app.application.use_cases.get_user_banks import GetUserBanksUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.process_uploaded_image import ProcessUploadedImageUseCase
from app.application.use_cases.quick_add_bank import QuickAddBankUseCase
from app.application.use_cases.ranking_snapshot import RankingSnapshotUseCase
from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.application.use_cases.save_bank_draft import SaveBankDraftUseCase
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.application.use_cases.change_language import ChangeLanguageUseCase
from app.application.use_cases.delete_bank import DeleteBankUseCase
from app.application.use_cases.delete_category import DeleteCategoryUseCase
from app.application.use_cases.get_ranking import GetRankingUseCase
from app.application.use_cases.parse_manual_cashback import ParseManualCashbackUseCase
from app.application.use_cases.toggle_notifications import ToggleNotificationsUseCase
from openai import APIError

from app.application.contracts.ports import OCRPort
from app.bootstrap.config import Settings
from app.domain.enums import OCRProvider
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CoreContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    categories: CategoryService
    parser: ParserService
    ranking: RankingService
    ocr: OCRPort
    clock: SystemClock


def _build_tesseract(settings: Settings) -> TesseractOCRAdapter:
    return TesseractOCRAdapter(
        tesseract_path=settings.tesseract_path,
        timeout=settings.ocr_timeout,
        max_file_size=settings.max_file_size,
        temp_dir=settings.temp_dir,
    )


def _build_openai_vision(settings: Settings) -> OpenAIVisionOCRAdapter:
    return OpenAIVisionOCRAdapter(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_vision_timeout,
        max_file_size=settings.max_file_size,
        max_tokens=settings.openai_vision_max_tokens,
    )


def _build_ocr_adapter(settings: Settings) -> OCRPort:
    raw_provider = (settings.ocr_provider or "auto").strip().lower()
    try:
        provider = OCRProvider(raw_provider)
    except ValueError as error:
        valid = ", ".join(item.value for item in OCRProvider)
        raise ValueError(f"Unknown OCR_PROVIDER={raw_provider!r}; expected one of: {valid}") from error

    has_openai_key = bool(settings.openai_api_key.strip())

    if provider is OCRProvider.TESSERACT:
        logger.info("OCR provider: tesseract (explicit)")
        return _build_tesseract(settings)

    if provider is OCRProvider.OPENAI:
        if not has_openai_key:
            raise ValueError("OCR_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        logger.info(
            "OCR provider: openai-vision (model=%s, base_url=%s)",
            settings.openai_model,
            settings.openai_base_url or "default",
        )
        return _build_openai_vision(settings)

    # OCRProvider.AUTO — prefer OpenAI vision when the key is set, else fall back to Tesseract.
    if has_openai_key:
        try:
            adapter = _build_openai_vision(settings)
        except (ImportError, APIError, ValueError) as error:  # pragma: no cover - defensive
            logger.warning("OpenAI vision OCR unavailable, falling back to tesseract: %s", error)
            return _build_tesseract(settings)
        logger.info(
            "OCR provider: openai-vision (auto, model=%s, base_url=%s)",
            settings.openai_model,
            settings.openai_base_url or "default",
        )
        return adapter

    logger.info("OCR provider: tesseract (auto, OPENAI_API_KEY not set)")
    return _build_tesseract(settings)


def build_core_container(settings: Settings) -> CoreContainer:
    engine, session_factory = create_session_factory(
        settings.sqlalchemy_database_uri,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    uow_factory = build_uow_factory(session_factory)
    categories = CategoryService()
    parser = ParserService(categories)
    ranking = RankingService(categories)
    ocr = _build_ocr_adapter(settings)
    clock = SystemClock(settings.app_timezone)
    return CoreContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        uow_factory=uow_factory,
        categories=categories,
        parser=parser,
        ranking=ranking,
        ocr=ocr,
        clock=clock,
    )


def build_application_facade(core: CoreContainer, reminder_sender: ReminderSenderPort) -> ApplicationFacade:
    password_hasher = Argon2PasswordHasher()
    register_local_user = RegisterLocalUserUseCase(core.uow_factory, password_hasher, default_language=core.settings.lang_default)
    authenticate_local_user = AuthenticateLocalUserUseCase(core.uow_factory, password_hasher)
    authenticate_external_identity = AuthenticateExternalIdentityUseCase(core.uow_factory, default_language=core.settings.lang_default)
    link_external_identity = LinkExternalIdentityUseCase(core.uow_factory)
    unlink_external_identity = UnlinkExternalIdentityUseCase(core.uow_factory)
    get_user_account = GetUserAccountUseCase(core.uow_factory)
    list_external_identities = ListExternalIdentitiesUseCase(core.uow_factory)
    sync_user = SyncTelegramUserUseCase(core.uow_factory, default_language=core.settings.lang_default)
    parse_manual = ParseManualCashbackUseCase(core.parser)
    process_uploaded_image = ProcessUploadedImageUseCase(core.ocr, core.parser)
    save_bank_draft = SaveBankDraftUseCase(core.uow_factory)
    get_user_banks = GetUserBanksUseCase(core.uow_factory)
    get_bank_details = GetBankDetailsUseCase(core.uow_factory)
    delete_bank = DeleteBankUseCase(core.uow_factory)
    delete_category = DeleteCategoryUseCase(core.uow_factory, core.categories)
    get_ranking = GetRankingUseCase(core.uow_factory, core.ranking)
    get_history = GetHistoryUseCase(core.uow_factory)
    change_language = ChangeLanguageUseCase(core.uow_factory)
    toggle_notifications = ToggleNotificationsUseCase(core.uow_factory)
    log_event = LogEventUseCase(core.uow_factory)
    find_user_by_identity = FindUserByExternalIdentityUseCase(core.uow_factory)
    best_card_for_category = BestCardForCategoryUseCase(core.uow_factory, core.ranking, core.categories)
    quick_add_bank = QuickAddBankUseCase(core.parser, save_bank_draft)
    ranking_snapshot = RankingSnapshotUseCase(core.uow_factory, core.ranking, core.categories)
    handle_command = HandleCommandUseCase(
        uow_factory=core.uow_factory,
        parser=core.parser,
        categories=core.categories,
        ranking=core.ranking,
        ocr=core.ocr,
        parse_manual_use_case=parse_manual,
        process_uploaded_image_use_case=process_uploaded_image,
        save_bank_draft_use_case=save_bank_draft,
        get_user_banks_use_case=get_user_banks,
        get_bank_details_use_case=get_bank_details,
        delete_bank_use_case=delete_bank,
        delete_category_use_case=delete_category,
        get_ranking_use_case=get_ranking,
        get_history_use_case=get_history,
        change_language_use_case=change_language,
        toggle_notifications_use_case=toggle_notifications,
        log_event_use_case=log_event,
    )
    reminders = SendMonthlyRemindersUseCase(
        uow_factory=core.uow_factory,
        sender=reminder_sender,
        clock=core.clock,
        reminder_hour=core.settings.reminder_hour,
    )
    return ApplicationFacade(
        register_local_user,
        authenticate_local_user,
        authenticate_external_identity,
        link_external_identity,
        unlink_external_identity,
        get_user_account,
        list_external_identities,
        sync_user,
        handle_command,
        reminders,
        log_event,
        find_user_by_identity,
        best_card_for_category,
        quick_add_bank,
        get_ranking,
        ranking_snapshot,
    )
