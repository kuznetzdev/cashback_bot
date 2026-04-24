from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.facade import ApplicationFacade
from app.bootstrap.config import Settings, get_settings
from app.bootstrap.container import CoreContainer, build_application_facade, build_core_container
from app.bootstrap.db_startup import ensure_database_exists
from app.bootstrap.logger import configure_logging
from app.i18n.localizer import Localizer

logger = logging.getLogger(__name__)


async def run_app() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    _validate_startup_settings(settings)

    await ensure_database_exists(settings)

    core = build_core_container(settings)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    localizer = Localizer(locales_dir=locales_dir, default_language=settings.lang_default)

    await _wait_for_database(
        core.engine,
        max_attempts=settings.db_connect_max_attempts,
        retry_delay=settings.db_connect_retry_delay,
    )
    await _run_migrations(
        database_url=settings.sqlalchemy_database_uri,
        enabled=settings.auto_migrate,
        max_attempts=settings.migration_max_attempts,
        retry_delay=settings.migration_retry_delay,
    )

    reminder_provider = _normalized_reminder_delivery_provider(settings)
    tasks: list[asyncio.Task[None]] = []
    telegram_bot = None
    if _telegram_bot_runtime_required(settings, reminder_provider):
        aiogram_module = importlib.import_module("aiogram")
        telegram_bot = aiogram_module.Bot(token=settings.bot_token)
    shared_facade = _build_runtime_facade(
        core=core,
        localizer=localizer,
        telegram_bot=telegram_bot,
        reminder_provider=reminder_provider,
    )
    if _reminder_delivery_runtime_enabled(reminder_provider):
        tasks.append(
            asyncio.create_task(
                _run_reminder_runtime(facade=shared_facade),
                name="reminder-runtime",
            )
        )
    if settings.app_enable_telegram:
        if telegram_bot is None:
            raise RuntimeError("Telegram bot runtime must be initialized before starting the Telegram adapter.")
        tasks.append(
            asyncio.create_task(
                _run_telegram_adapter(
                    settings=settings,
                    bot=telegram_bot,
                    facade=shared_facade,
                    localizer=localizer,
                ),
                name="telegram-adapter",
            )
        )
    if settings.app_enable_web:
        web_app_module = importlib.import_module("app.adapters.web.app")
        web_server_module = importlib.import_module("app.adapters.web.server")
        web_deps = web_app_module.WebDependencies(
            facade=shared_facade,
            localizer=localizer,
            default_language=settings.lang_default,
            temp_dir=settings.temp_dir,
            bot_token=settings.bot_token,
            bot_username=settings.telegram_bot_username,
            telegram_auth_enabled=settings.web_enable_telegram_auth,
            web_base_url=settings.web_base_url,
            max_upload_size=min(settings.web_max_upload_size, settings.max_file_size),
            secure_cookies=settings.web_secure_cookies,
            session_secret=settings.web_session_secret,
        )
        web_app = web_app_module.create_web_app(web_deps)
        tasks.append(
            asyncio.create_task(
                web_server_module.run_web_server(
                    web_app,
                    host=settings.web_host,
                    port=settings.web_port,
                    log_level=settings.log_level,
                ),
                name="web-adapter",
            )
        )
    try:
        logger.info(
            "Cashback Analyzer starting (telegram_adapter=%s, web_adapter=%s, reminder_provider=%s)",
            settings.app_enable_telegram,
            settings.app_enable_web,
            reminder_provider or "disabled",
        )
        if len(tasks) == 1:
            await tasks[0]
        else:
            await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Application runtime cancelled")
        raise
    finally:
        logger.info("Shutting down application...")
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if telegram_bot is not None:
            await telegram_bot.session.close()
        await core.engine.dispose()


async def _run_reminder_runtime(*, facade) -> None:
    scheduler_module = importlib.import_module("app.adapters.scheduler")
    reminder_loop = scheduler_module.ReminderLoop(facade.send_monthly_reminders)
    reminder_loop.start()
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Reminder runtime cancelled")
        raise
    finally:
        await reminder_loop.stop()


async def _run_telegram_adapter(
    *,
    settings: Settings,
    bot,
    facade,
    localizer: Localizer,
) -> None:
    aiogram_module = importlib.import_module("aiogram")
    memory_storage_module = importlib.import_module("aiogram.fsm.storage.memory")
    telegram_renderer_module = importlib.import_module("app.adapters.telegram.renderer")
    telegram_router_module = importlib.import_module("app.adapters.telegram.router")

    dp = aiogram_module.Dispatcher(storage=memory_storage_module.MemoryStorage())
    renderer = telegram_renderer_module.TelegramScreenRenderer(localizer=localizer)
    telegram_deps = telegram_router_module.TelegramDependencies(
        facade=facade,
        renderer=renderer,
        localizer=localizer,
        default_language=settings.lang_default,
    )
    dp.include_router(telegram_router_module.build_router(telegram_deps))
    try:
        await _run_polling_with_retry(
            dp=dp,
            bot=bot,
            retry_delay=settings.telegram_retry_delay,
        )
    finally:
        await dp.storage.close()


async def _wait_for_database(engine: AsyncEngine, *, max_attempts: int, retry_delay: float) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            logger.info("Database connection is ready.")
            return
        except (SQLAlchemyError, OSError) as error:
            logger.warning("Database not ready (attempt %s/%s): %s", attempt, max_attempts, error)
            if attempt == max_attempts:
                raise RuntimeError("Database connection failed after retries.") from error
            await asyncio.sleep(retry_delay)


async def _run_polling_with_retry(*, dp: object, bot: object, retry_delay: float) -> None:
    telegram_exceptions = importlib.import_module("aiogram.exceptions")

    while True:
        try:
            await dp.start_polling(bot)
            return
        except telegram_exceptions.TelegramUnauthorizedError:
            logger.critical("Telegram token is invalid (Unauthorized).")
            raise
        except (telegram_exceptions.TelegramNetworkError, telegram_exceptions.TelegramServerError) as error:
            logger.warning("Telegram polling transient error: %s. Retry in %.1f sec.", error, retry_delay)
            await asyncio.sleep(retry_delay)


async def _run_migrations(*, database_url: str, enabled: bool, max_attempts: int, retry_delay: float) -> None:
    if not enabled:
        logger.info("AUTO_MIGRATE disabled. Skip migrations.")
        return
    for attempt in range(1, max_attempts + 1):
        try:
            await asyncio.to_thread(_upgrade_head_sync, database_url)
            logger.info("Migrations applied successfully.")
            return
        except Exception as error:
            logger.warning("Migration attempt %s/%s failed: %s", attempt, max_attempts, error)
            if attempt == max_attempts:
                raise RuntimeError("Migration failed after retries.") from error
            await asyncio.sleep(retry_delay)


def _upgrade_head_sync(database_url: str) -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _build_runtime_facade(
    *,
    core: CoreContainer,
    localizer: Localizer,
    telegram_bot: object | None,
    reminder_provider: str | None,
) -> ApplicationFacade:
    if reminder_provider == "telegram":
        if telegram_bot is None:
            raise RuntimeError("Telegram bot runtime must be initialized before creating the telegram reminder sender.")
        telegram_sender_module = importlib.import_module("app.adapters.telegram.reminder_sender")
        reminder_sender = telegram_sender_module.TelegramReminderSender(bot=telegram_bot, localizer=localizer)
    else:
        system_module = importlib.import_module("app.adapters.system")
        reminder_sender = system_module.NoopReminderSender()
    return build_application_facade(core, reminder_sender, delivery_provider=reminder_provider)


def _validate_startup_settings(settings: Settings) -> None:
    reminder_provider = _normalized_reminder_delivery_provider(settings)
    if reminder_provider not in {None, "telegram"}:
        raise RuntimeError("REMINDER_DELIVERY_PROVIDER must be empty or 'telegram'.")
    if not settings.app_enable_telegram and not settings.app_enable_web:
        raise RuntimeError("At least one adapter must be enabled (APP_ENABLE_TELEGRAM or APP_ENABLE_WEB).")
    token = settings.bot_token.strip()
    telegram_token_required = _telegram_token_required(settings, reminder_provider)
    if telegram_token_required and (
        not token or token.endswith(":TEST_TOKEN") or "replace_me" in token.lower()
    ):
        raise RuntimeError("BOT_TOKEN is not configured. Set a valid Telegram bot token in .env or environment.")
    if settings.app_enable_web and settings.web_enable_telegram_auth and not settings.telegram_bot_username.strip():
        raise RuntimeError("TELEGRAM_BOT_USERNAME is required when APP_ENABLE_WEB=true.")
    if settings.app_enable_web and (
        settings.web_session_secret == "change-me-session-secret"
        or settings.web_session_secret.strip() == ""
    ):
        raise RuntimeError("WEB_SESSION_SECRET must be set to a non-default secret when APP_ENABLE_WEB=true.")


def _normalized_reminder_delivery_provider(settings: Settings) -> str | None:
    raw_provider = settings.reminder_delivery_provider
    if raw_provider is None:
        return None
    normalized_provider = raw_provider.strip().lower()
    return normalized_provider or None


def _telegram_token_required(settings: Settings, reminder_provider: str | None) -> bool:
    return (
        settings.app_enable_telegram
        or reminder_provider == "telegram"
        or (settings.app_enable_web and settings.web_enable_telegram_auth)
    )


def _telegram_bot_runtime_required(settings: Settings, reminder_provider: str | None) -> bool:
    return settings.app_enable_telegram or reminder_provider == "telegram"


def _reminder_delivery_runtime_enabled(reminder_provider: str | None) -> bool:
    return reminder_provider is not None
