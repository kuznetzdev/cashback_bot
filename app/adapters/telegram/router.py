from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.adapters.telegram.callbacks import decode_callback
from app.adapters.telegram.localizer import Localizer
from app.adapters.telegram.renderer import TelegramScreenRenderer
from app.adapters.telegram.state import load_workflow_state, save_workflow_state
from app.application import ApplicationFacade
from app.application.models import Effect, UserCommand, UserContext
from app.domain.errors import DomainError
from app.domain.models import UserProfile

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramDependencies:
    facade: ApplicationFacade
    renderer: TelegramScreenRenderer
    localizer: Localizer
    temp_dir: Path
    default_language: str


def build_router(deps: TelegramDependencies) -> Router:
    router = Router(name="cashback_analyzer")

    @router.message(CommandStart())
    async def on_start(message: Message, state: FSMContext) -> None:
        await _handle_event(
            deps=deps,
            event=message,
            state=state,
            command=UserCommand(name="start"),
            log_action="user_started",
            reset_state=False,
        )

    @router.callback_query(F.data.startswith("nav:"))
    async def on_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None:
            await _answer_callback_safely(callback)
            await deps.renderer.notify_error(callback, deps.localizer.t("errors.unknown_command", deps.default_language))
            return
        try:
            command = decode_callback(callback.data)
        except DomainError as error:
            await _answer_callback_safely(callback)
            await deps.renderer.notify_error(
                callback,
                deps.localizer.t(error.message_key, deps.default_language, error.payload),
            )
            return
        await _handle_event(deps=deps, event=callback, state=state, command=command)

    @router.message(F.photo)
    async def on_photo(message: Message, state: FSMContext) -> None:
        user = await _sync_user_only(deps, message)
        workflow = await load_workflow_state(state)
        if workflow.pending_input_kind != "photo_upload":
            await deps.renderer.notify_error(
                message,
                deps.localizer.t("errors.send_photo_or_text", user.language),
            )
            return

        status: Message | None = None
        deps.temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = deps.temp_dir / f"tg_{uuid4().hex}.jpg"
        try:
            status = await deps.renderer.notify_status(message, deps.localizer.t("messages.processing", user.language))
            photo = message.photo[-1]
            await message.bot.download(photo, destination=temp_path)
            await _handle_event(
                deps=deps,
                event=message,
                state=state,
                command=UserCommand(name="submit_photo_path", payload={"path": str(temp_path)}),
                known_user=user,
            )
        except (RuntimeError, OSError) as error:
            logger.exception("Photo flow failed: %s", error)
            await _safe_log_event(
                deps=deps,
                user=user,
                action="error_photo_flow",
                payload={"details": str(error)},
            )
            await deps.renderer.notify_error(message, deps.localizer.t("errors.unexpected", user.language))
        except Exception as error:
            logger.exception("Unhandled photo flow error: %s", error)
            await _safe_log_event(
                deps=deps,
                user=user,
                action="error_photo_flow_unhandled",
                payload={"details": str(error)},
            )
            await deps.renderer.notify_error(message, deps.localizer.t("errors.unexpected", user.language))
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as error:
                logger.warning("Failed to cleanup telegram temp file %s: %s", temp_path, error)
            if status is not None:
                try:
                    await status.delete()
                except TelegramBadRequest as error:
                    logger.debug("Failed to delete temporary status message: %s", error)

    @router.message(F.text)
    async def on_text(message: Message, state: FSMContext) -> None:
        text = message.text or ""
        command = _map_text_to_command(text)
        await _handle_event(deps=deps, event=message, state=state, command=command)

    return router


async def _handle_event(
    *,
    deps: TelegramDependencies,
    event: Message | CallbackQuery,
    state: FSMContext,
    command: UserCommand,
    log_action: str | None = None,
    reset_state: bool = False,
    known_user: UserProfile | None = None,
) -> None:
    user = known_user
    language = deps.default_language
    try:
        if user is None:
            user = await _sync_user_only(deps, event, log_action=log_action)
        language = user.language
        if reset_state:
            await state.clear()
        workflow = await load_workflow_state(state)
        result = await deps.facade.handle_command(user, workflow, command)
        await save_workflow_state(state, result.state)
        await deps.renderer.render(event=event, state=state, screen=result.screen, language=result.user.language)
        await _apply_effects(deps=deps, event=event, user=result.user, language=result.user.language, effects=result.effects)
    except DomainError as error:
        logger.info("Domain error: %s", error.message_key)
        await _safe_log_event(
            deps=deps,
            user=user,
            action="error_handled",
            payload={"error_key": error.message_key, "command": command.name},
        )
        await _answer_callback_safely(event)
        await deps.renderer.notify_error(event, deps.localizer.t(error.message_key, language, error.payload))
    except RuntimeError as error:
        logger.exception("Runtime error while handling event: %s", error)
        await _safe_log_event(
            deps=deps,
            user=user,
            action="error_runtime",
            payload={"command": command.name, "details": str(error)},
        )
        await _answer_callback_safely(event)
        await deps.renderer.notify_error(event, deps.localizer.t("errors.unexpected", language))
    except OSError as error:
        logger.exception("I/O error while handling event: %s", error)
        await _safe_log_event(
            deps=deps,
            user=user,
            action="error_io",
            payload={"command": command.name, "details": str(error)},
        )
        await _answer_callback_safely(event)
        await deps.renderer.notify_error(event, deps.localizer.t("errors.unexpected", language))
    except Exception as error:
        logger.exception("Unhandled error while handling event: %s", error)
        await _safe_log_event(
            deps=deps,
            user=user,
            action="error_unhandled",
            payload={"command": command.name, "details": str(error)},
        )
        await _answer_callback_safely(event)
        await deps.renderer.notify_error(event, deps.localizer.t("errors.unexpected", language))


async def _sync_user_only(
    deps: TelegramDependencies,
    event: Message | CallbackQuery,
    *,
    log_action: str | None = None,
) -> UserProfile:
    if isinstance(event, Message):
        from_user = event.from_user
    else:
        from_user = event.from_user
    if from_user is None:
        raise RuntimeError("Update does not have from_user")
    context = UserContext(
        external_user_id=from_user.id,
        username=from_user.username,
        full_name=from_user.full_name,
    )
    return await deps.facade.sync_user(context, log_action=log_action)


def _map_text_to_command(text: str) -> UserCommand:
    normalized = text.strip()
    if normalized == "/help":
        return UserCommand(name="open_help")
    if normalized == "/home":
        return UserCommand(name="open_home")
    if normalized == "/top":
        return UserCommand(name="open_top")
    if normalized == "/settings":
        return UserCommand(name="open_settings")
    if normalized == "/banks":
        return UserCommand(name="open_my_banks")
    if normalized == "/cancel":
        return UserCommand(name="cancel_flow")
    return UserCommand(name="submit_text", payload={"text": text})


async def _apply_effects(
    *,
    deps: TelegramDependencies,
    event: Message | CallbackQuery,
    user: UserProfile,
    language: str,
    effects: list[Effect],
) -> None:
    for effect in effects:
        try:
            if effect.kind == "show_status":
                message_key = str(effect.payload.get("message_key", ""))
                if not message_key:
                    continue
                text = deps.localizer.t(message_key, language, effect.payload)
                await deps.renderer.notify_status(event, text, delete_after=bool(effect.payload.get("transient", False)))
                continue
            if effect.kind == "log_event":
                action = str(effect.payload.get("action", ""))
                if not action:
                    continue
                payload_obj = effect.payload.get("payload")
                payload: dict[str, object] | None = payload_obj if isinstance(payload_obj, dict) else None
                await deps.facade.log_event(user_id=user.id, action=action, payload=payload)
        except Exception as error:
            logger.warning("Failed to apply effect %s: %s", effect.kind, error)


async def _safe_log_event(
    *,
    deps: TelegramDependencies,
    user: UserProfile | None,
    action: str,
    payload: dict[str, object] | None = None,
) -> None:
    if user is None:
        return
    try:
        await deps.facade.log_event(user_id=user.id, action=action, payload=payload)
    except Exception as error:
        logger.warning("Failed to persist error event %s: %s", action, error)


async def _answer_callback_safely(event: Message | CallbackQuery) -> None:
    if not isinstance(event, CallbackQuery):
        return
    try:
        await event.answer()
    except TelegramBadRequest:
        return
