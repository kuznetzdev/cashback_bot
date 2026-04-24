from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User as TelegramUser

from app.adapters.telegram.callbacks import decode_callback
from app.adapters.telegram.renderer import TelegramScreenRenderer
from app.application.facade import ApplicationFacade
from app.application.auth.models import ExternalIdentityContext
from app.application.dto.media import ImageUpload
from app.application.workflow.models import Effect, UserCommand
from app.domain.errors import DomainError
from app.domain.models import UserAccount
from app.i18n.localizer import Localizer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramDependencies:
    facade: ApplicationFacade
    renderer: TelegramScreenRenderer
    localizer: Localizer
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

        status: Message | None = None
        try:
            status = await deps.renderer.notify_status(message, deps.localizer.t("messages.processing", user.language))
            photo = message.photo[-1]
            buffer = io.BytesIO()
            await message.bot.download(photo, destination=buffer)
            await _handle_event(
                deps=deps,
                event=message,
                state=state,
                command=UserCommand(
                    name="submit_uploaded_image",
                    payload={
                        "upload": ImageUpload(
                            content=buffer.getvalue(),
                            filename=f"telegram_{photo.file_unique_id}.jpg",
                            content_type="image/jpeg",
                        )
                    },
                ),
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
    known_user: UserAccount | None = None,
) -> None:
    user = known_user
    language = deps.default_language
    try:
        if user is None:
            user = await _sync_user_only(deps, event, log_action=log_action)
        language = user.language
        if reset_state:
            await state.clear()
        workflow = await deps.facade.get_workflow_state(user_id=user.id)
        if command.name == "start" and not workflow.is_empty():
            result = await deps.facade.resume_workflow(user, workflow)
        else:
            result = await deps.facade.handle_command(user, workflow, command)
        await deps.facade.save_workflow_state(user_id=result.user.id, state=result.state)
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
) -> UserAccount:
    if isinstance(event, Message):
        from_user = event.from_user
    else:
        from_user = event.from_user
    if from_user is None:
        raise RuntimeError("Update does not have from_user")
    identity = _build_telegram_identity(from_user)
    return await deps.facade.authenticate_external_identity(
        identity,
        create_user_if_missing=True,
        log_action=log_action,
    )


def _build_telegram_identity(from_user: TelegramUser) -> ExternalIdentityContext:
    return ExternalIdentityContext(
        provider="telegram",
        provider_user_id=str(from_user.id),
        provider_username=from_user.username,
        provider_display_name=from_user.full_name,
    )


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
    user: UserAccount,
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
    user: UserAccount | None,
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
