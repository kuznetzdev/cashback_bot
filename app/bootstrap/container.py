from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.ocr_tesseract import TesseractOCRAdapter
from app.adapters.postgres.session import create_session_factory
from app.adapters.postgres.uow import SqlAlchemyUnitOfWork, build_uow_factory
from app.adapters.system import SystemClock
from app.application import ApplicationFacade
from app.application.contracts.ports import ReminderSenderPort
from app.application.use_cases.handle_command import HandleCommandUseCase
from app.application.use_cases.log_event import LogEventUseCase
from app.application.use_cases.send_monthly_reminders import SendMonthlyRemindersUseCase
from app.application.use_cases.sync_user import SyncTelegramUserUseCase
from app.bootstrap.config import Settings
from app.domain.services.categories import CategoryService
from app.domain.services.parsing import ParserService
from app.domain.services.ranking import RankingService


@dataclass(slots=True)
class CoreContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    categories: CategoryService
    parser: ParserService
    ranking: RankingService
    ocr: TesseractOCRAdapter
    clock: SystemClock


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
    ocr = TesseractOCRAdapter(
        tesseract_path=settings.tesseract_path,
        timeout=settings.ocr_timeout,
        max_file_size=settings.max_file_size,
        temp_dir=settings.temp_dir,
    )
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
    sync_user = SyncTelegramUserUseCase(core.uow_factory, default_language=core.settings.lang_default)
    handle_command = HandleCommandUseCase(
        uow_factory=core.uow_factory,
        parser=core.parser,
        categories=core.categories,
        ranking=core.ranking,
        ocr=core.ocr,
    )
    reminders = SendMonthlyRemindersUseCase(
        uow_factory=core.uow_factory,
        sender=reminder_sender,
        clock=core.clock,
        reminder_hour=core.settings.reminder_hour,
    )
    log_event = LogEventUseCase(core.uow_factory)
    return ApplicationFacade(sync_user, handle_command, reminders, log_event)
