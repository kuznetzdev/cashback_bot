from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramServerError, TelegramUnauthorizedError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.scheduler import ReminderLoop
from app.adapters.system import NoopReminderSender
from app.adapters.telegram.rate_limit import TokenBucketRateLimiter
from app.adapters.telegram.reminder_sender import TelegramReminderSender
from app.adapters.telegram.renderer import TelegramScreenRenderer
from app.adapters.telegram.router import TelegramDependencies, build_router
from app.adapters.web.app import WebDependencies, create_web_app
from app.adapters.web.server import run_web_server
from app.application import ApplicationFacade
from app.bootstrap.config import Settings, get_settings
from app.bootstrap.container import build_application_facade, build_core_container
from app.bootstrap.db_startup import ensure_database_exists
from app.bootstrap.logger import configure_logging
from app.bootstrap.metrics import MetricsRegistry, build_metrics_registry
from app.i18n.localizer import Localizer

logger = logging.getLogger(__name__)


async def run_app() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    _validate_startup_settings(settings)

    await ensure_database_exists(settings)

    # One metrics registry for the whole process — wired into the OCR adapter
    # (so `cashback_bot_ocr_calls_total` is actually populated) and handed to
    # the web app / telegram router so their middleware hits the same counters.
    metrics = build_metrics_registry()
    core = build_core_container(settings, metrics=metrics)
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

    tasks: list[asyncio.Task[None]] = []
    telegram_facade = None
    bot: Bot | None = None
    dispatcher: Dispatcher | None = None
    use_webhook = settings.app_enable_telegram and settings.app_enable_web and settings.webhook_enabled
    if settings.app_enable_telegram:
        bot = Bot(token=settings.bot_token)
        reminder_sender = TelegramReminderSender(bot=bot, localizer=localizer)
        telegram_facade = build_application_facade(core, reminder_sender)
        if use_webhook:
            # Build the dispatcher here so the web app can feed updates directly
            # into it instead of running polling. The reminder loop still runs
            # as a side task so monthly reminders fire under webhook mode too.
            dispatcher = _build_dispatcher(
                settings=settings,
                facade=telegram_facade,
                localizer=localizer,
                metrics=metrics,
            )
            reminder_loop = ReminderLoop(telegram_facade.send_monthly_reminders)
            reminder_loop.start()
            tasks.append(
                asyncio.create_task(
                    _run_webhook_adapter(
                        settings=settings,
                        bot=bot,
                        dp=dispatcher,
                        localizer=localizer,
                        reminder_loop=reminder_loop,
                    ),
                    name="telegram-webhook-adapter",
                )
            )
        else:
            tasks.append(
                asyncio.create_task(
                    _run_telegram_adapter(
                        settings=settings,
                        bot=bot,
                        facade=telegram_facade,
                        localizer=localizer,
                        metrics=metrics,
                    ),
                    name="telegram-adapter",
                )
            )
    if settings.app_enable_web:
        web_facade = telegram_facade or build_application_facade(core, NoopReminderSender())
        web_deps = WebDependencies(
            facade=web_facade,
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
            webhook_path=settings.webhook_path,
            webhook_secret=settings.webhook_secret,
            bot=bot if use_webhook else None,
            dispatcher=dispatcher if use_webhook else None,
            cors_origins=settings.cors_origins,
            metrics_token=settings.metrics_token,
            api_rate_limit_per_minute=settings.api_rate_limit_per_minute,
            db_ping=_make_db_ping(core.engine),
            telegram_ping=_make_telegram_ping(bot) if bot is not None else None,
            ocr_provider_name=settings.ocr_provider,
            app_version=_resolve_app_version(),
            metrics=metrics,
        )
        web_app = create_web_app(web_deps)
        tasks.append(
            asyncio.create_task(
                run_web_server(
                    web_app,
                    host=settings.web_host,
                    port=settings.web_port,
                    log_level=settings.log_level,
                ),
                name="web-adapter",
            )
        )
    shutdown_event = asyncio.Event()
    _install_signal_handlers(shutdown_event)
    try:
        logger.info(
            "Cashback Analyzer starting (telegram=%s, web=%s)",
            settings.app_enable_telegram,
            settings.app_enable_web,
        )
        # Race the adapter tasks against the shutdown signal. The first of them
        # to resolve wins; the rest are cancelled in the finally block so
        # a SIGTERM cleanly tears down polling + web + reminder loop.
        await _await_until_shutdown_or_failure(tasks, shutdown_event)
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
        await _close_ocr_adapter(core.ocr)
        await core.engine.dispose()


async def _close_ocr_adapter(adapter: object) -> None:
    # Works for composite (delegates to wrapped adapters) and for direct
    # OpenAI vision. Tesseract has no pool to release; a missing close() is
    # expected and harmless.
    for target in (adapter, getattr(adapter, "_fallback", None), getattr(adapter, "_primary", None)):
        if target is None:
            continue
        closer = getattr(target, "close", None)
        if callable(closer):
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as error:  # pragma: no cover - best-effort cleanup
                logger.debug("OCR adapter close raised: %s", error)


def _install_signal_handlers(event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, event.set)
        except NotImplementedError:
            # Windows / certain embedded environments — rely on KeyboardInterrupt.
            logger.debug("Signal %s not installable on this loop", sig)


async def _await_until_shutdown_or_failure(
    tasks: list[asyncio.Task[None]],
    shutdown_event: asyncio.Event,
) -> None:
    shutdown_task = asyncio.create_task(shutdown_event.wait(), name="shutdown-waiter")
    awaitables: list[asyncio.Task[object]] = [*tasks, shutdown_task]
    try:
        done, _pending = await asyncio.wait(awaitables, return_when=asyncio.FIRST_COMPLETED)
    finally:
        if not shutdown_task.done():
            shutdown_task.cancel()
    # Surface any adapter-task exception so the caller logs it and exits non-zero.
    for completed in done:
        if completed is shutdown_task:
            continue
        if completed.cancelled():
            continue
        exc = completed.exception()
        if exc is not None:
            raise exc


def _build_dispatcher(
    *,
    settings: Settings,
    facade: ApplicationFacade,
    localizer: Localizer,
    metrics: MetricsRegistry | None = None,
) -> Dispatcher:
    """Factor out dispatcher/router construction so polling and webhook modes
    share the identical wiring. The only thing that changes between them is
    how updates reach this dispatcher."""
    dp = Dispatcher(storage=build_fsm_storage(settings))
    renderer = TelegramScreenRenderer(localizer=localizer)
    telegram_deps = TelegramDependencies(
        facade=facade,
        renderer=renderer,
        localizer=localizer,
        default_language=settings.lang_default,
        bot_username=settings.telegram_bot_username or None,
        # Burst 5 photos, refill 1 every 10s. Enough for normal use (swap cards,
        # reshoot a blurry photo) while capping abuse at ~6 photos/minute/user.
        photo_rate_limiter=TokenBucketRateLimiter(capacity=5, refill_per_second=0.1),
        metrics=metrics,
    )
    dp.include_router(build_router(telegram_deps))
    return dp


async def _run_telegram_adapter(
    *,
    settings: Settings,
    bot: Bot,
    facade: ApplicationFacade,
    localizer: Localizer,
    metrics: MetricsRegistry | None = None,
) -> None:
    dp = _build_dispatcher(settings=settings, facade=facade, localizer=localizer, metrics=metrics)
    reminder_loop = ReminderLoop(facade.send_monthly_reminders)
    reminder_loop.start()
    try:
        await _publish_bot_command_menu(bot=bot, localizer=localizer, default_language=settings.lang_default)
        # Make sure no old webhook is lingering — switching from webhook back to
        # polling without deleting it leaves Telegram sending updates to a URL
        # that now 404s, while polling returns nothing.
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception as error:  # pragma: no cover - best-effort cleanup
            logger.debug("delete_webhook() pre-poll failed: %s", error)
        await _run_polling_with_retry(
            dp=dp,
            bot=bot,
            retry_delay=settings.telegram_retry_delay,
        )
    finally:
        await reminder_loop.stop()
        await dp.storage.close()
        await bot.session.close()


async def _run_webhook_adapter(
    *,
    settings: Settings,
    bot: Bot,
    dp: Dispatcher,
    localizer: Localizer,
    reminder_loop: ReminderLoop,
) -> None:
    """Register the webhook with Telegram and then keep the adapter task alive
    so the shared shutdown path can tear down the reminder loop and bot
    session cleanly. The FastAPI app is the one actually dispatching updates."""
    try:
        await _publish_bot_command_menu(bot=bot, localizer=localizer, default_language=settings.lang_default)
        url = f"{settings.web_base_url.rstrip('/')}{settings.webhook_path}"
        await bot.set_webhook(
            url=url,
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=True,
        )
        logger.info("Webhook set: %s", url)
        # Park the task — the FastAPI app does the actual dispatch. We only
        # exit when cancelled (shutdown) or if the bot session dies.
        await asyncio.Event().wait()
    finally:
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception as error:  # pragma: no cover - best-effort
            logger.debug("delete_webhook() on shutdown failed: %s", error)
        await reminder_loop.stop()
        await dp.storage.close()
        await bot.session.close()


def _make_db_ping(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    async def ping() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return ping


def _make_telegram_ping(bot: Bot):  # type: ignore[no-untyped-def]
    async def ping() -> None:
        await bot.get_me()

    return ping


def _resolve_app_version() -> str:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0:
            return out.stdout.strip() or "dev"
    except Exception:  # pragma: no cover - best-effort
        pass
    return "dev"


async def _publish_bot_command_menu(*, bot: Bot, localizer: Localizer, default_language: str) -> None:
    try:
        # Every command here MUST have a matching handler in the router.
        # /home and /cancel are handled via the F.text fallback (see
        # `_map_text_to_command`) so autocomplete surfaces them too.
        commands = [
            BotCommand(command="start", description=localizer.t("commands.start", default_language)),
            BotCommand(command="best", description=localizer.t("commands.best", default_language)),
            BotCommand(command="quickadd", description=localizer.t("commands.quickadd", default_language)),
            BotCommand(command="banks", description=localizer.t("commands.banks", default_language)),
            BotCommand(command="top", description=localizer.t("commands.top", default_language)),
            BotCommand(command="home", description=localizer.t("commands.home", default_language)),
            BotCommand(command="cancel", description=localizer.t("commands.cancel", default_language)),
            BotCommand(command="settings", description=localizer.t("commands.settings", default_language)),
            BotCommand(command="export", description=localizer.t("commands.export", default_language)),
            BotCommand(command="help", description=localizer.t("commands.help", default_language)),
        ]
        await bot.set_my_commands(commands)
    except Exception as error:  # pragma: no cover - non-blocking UX polish
        logger.warning("Failed to publish bot command menu: %s", error)


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


async def _run_polling_with_retry(*, dp: Dispatcher, bot: Bot, retry_delay: float) -> None:
    while True:
        try:
            await dp.start_polling(bot)
            return
        except TelegramUnauthorizedError:
            logger.critical("Telegram token is invalid (Unauthorized).")
            raise
        except (TelegramNetworkError, TelegramServerError) as error:
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


def build_fsm_storage(settings: Settings) -> BaseStorage:
    """Select aiogram FSM storage based on settings.

    Redis is preferred in production so per-user wizard progress survives bot
    restarts. Memory storage is fine locally and in tests but loses state on
    every deploy / crash. If ``FSM_STORAGE=redis`` but ``REDIS_URL`` is unset
    we fall back to memory with a loud warning rather than crashing, so the bot
    still boots in a degraded but usable mode.

    When Redis is selected we wrap it in :class:`ResilientFSMStorage` so a
    runtime Redis outage falls back to in-memory state for the duration of
    the outage instead of raising on every user interaction.
    """
    storage_kind = settings.fsm_storage
    if storage_kind == "redis":
        redis_url = (settings.redis_url or "").strip()
        if not redis_url:
            logger.warning("FSM_STORAGE=redis but REDIS_URL is empty — falling back to MemoryStorage.")
            return MemoryStorage()
        # Imported lazily so installations without the redis extra still run
        # with MemoryStorage.
        from aiogram.fsm.storage.redis import RedisStorage

        from app.adapters.telegram.resilient_storage import ResilientFSMStorage

        primary = RedisStorage.from_url(redis_url, key_prefix="cashback_fsm:")
        storage = ResilientFSMStorage(primary)
        logger.info("FSM storage: redis (%s) with in-memory fallback", redis_url)
        return storage
    logger.info("FSM storage: memory")
    return MemoryStorage()


def _validate_startup_settings(settings: Settings) -> None:
    if not settings.app_enable_telegram and not settings.app_enable_web:
        raise RuntimeError("At least one adapter must be enabled (APP_ENABLE_TELEGRAM or APP_ENABLE_WEB).")
    token = settings.bot_token.strip()
    telegram_token_required = settings.app_enable_telegram or (
        settings.app_enable_web and settings.web_enable_telegram_auth
    )
    if telegram_token_required and (
        not token or token.endswith(":TEST_TOKEN") or "replace_me" in token.lower()
    ):
        raise RuntimeError(
            "BOT_TOKEN is not configured. Set a valid Telegram bot token in .env or environment."
        )
    if (
        settings.app_enable_web
        and settings.web_enable_telegram_auth
        and not settings.telegram_bot_username.strip()
    ):
        raise RuntimeError("TELEGRAM_BOT_USERNAME is required when APP_ENABLE_WEB=true.")
    if settings.app_enable_web and (
        settings.web_session_secret == "change-me-session-secret" or settings.web_session_secret.strip() == ""
    ):
        raise RuntimeError("WEB_SESSION_SECRET must be set to a non-default secret when APP_ENABLE_WEB=true.")
    # Fail-fast on OCR misconfiguration so the bot doesn't start in a state
    # where the first photo upload would crash the OCR path in production.
    ocr_provider = (settings.ocr_provider or "auto").strip().lower()
    if ocr_provider == "openai" and not settings.openai_api_key.strip():
        raise RuntimeError(
            "OCR_PROVIDER=openai requires OPENAI_API_KEY. "
            "Set the key or switch OCR_PROVIDER to 'auto' / 'tesseract'."
        )
