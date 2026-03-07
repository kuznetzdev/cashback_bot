from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.adapters.telegram.localizer import Localizer
from app.adapters.web.auth import verify_telegram_login
from app.application import ApplicationFacade
from app.application.models import Action, Effect, Screen, UserCommand, UserContext, WorkflowResult, WorkflowState
from app.domain.errors import DomainError
from app.domain.models import UserProfile

logger = logging.getLogger(__name__)

SESSION_USER_KEY = "web_user"
SESSION_STATE_KEY = "workflow_state"
SESSION_SCREEN_KEY = "screen_cache"
DEFAULT_ACTIONS_LIMIT = 8


@dataclass(slots=True)
class WebDependencies:
    facade: ApplicationFacade
    localizer: Localizer
    default_language: str
    temp_dir: Path
    bot_token: str
    bot_username: str
    web_base_url: str
    max_upload_size: int
    secure_cookies: bool
    session_secret: str


def create_web_app(deps: WebDependencies) -> FastAPI:
    app = FastAPI(title="Cashback Analyzer Web", docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=deps.session_secret,
        same_site="lax",
        https_only=deps.secure_cookies,
        session_cookie="cashback_session",
        max_age=60 * 60 * 24 * 14,
    )

    root_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(root_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(root_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> Response:
        user = _get_user_from_session(request)
        if user is not None:
            return RedirectResponse(url="/app", status_code=303)
        language = deps.default_language
        callback_url = f"{deps.web_base_url.rstrip('/')}/auth/telegram/callback"
        return templates.TemplateResponse(
            request=request,
            name="landing.html",
            context={
                "language": language,
                "title": "Cashback Analyzer",
                "subtitle": deps.localizer.t("messages.web_login_hint", language),
                "bot_username": deps.bot_username,
                "auth_url": callback_url,
            },
        )

    @app.get("/auth/telegram/callback")
    async def telegram_callback(request: Request) -> Response:
        payload = {key: value for key, value in request.query_params.items()}
        try:
            auth = verify_telegram_login(payload, bot_token=deps.bot_token)
            context = UserContext(
                external_user_id=auth.telegram_id,
                username=auth.username,
                full_name=auth.full_name,
            )
            user = await deps.facade.sync_user(context, log_action="web_login")
            result = await deps.facade.handle_command(user, WorkflowState(), UserCommand(name="open_home"))
            _persist_workflow(request, result)
            return RedirectResponse(url="/app", status_code=303)
        except DomainError as error:
            language = deps.default_language
            callback_url = f"{deps.web_base_url.rstrip('/')}/auth/telegram/callback"
            return templates.TemplateResponse(
                request=request,
                name="landing.html",
                context={
                    "language": language,
                    "title": "Cashback Analyzer",
                    "subtitle": deps.localizer.t("messages.web_login_hint", language),
                    "bot_username": deps.bot_username,
                    "auth_url": callback_url,
                    "error_message": deps.localizer.t(error.message_key, language, error.payload),
                },
                status_code=401,
            )

    @app.post("/auth/logout")
    async def logout(request: Request) -> Response:
        request.session.clear()
        return RedirectResponse(url="/", status_code=303)

    @app.get("/app", response_class=HTMLResponse)
    async def app_home(request: Request) -> Response:
        user = _get_user_from_session(request)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        state = _get_state_from_session(request)
        screen = _get_screen_from_session(request)
        if screen is None:
            result = await deps.facade.handle_command(user, state, UserCommand(name="open_home"))
            _persist_workflow(request, result)
            user = result.user
            state = result.state
            screen = result.screen
        return templates.TemplateResponse(
            request=request,
            name="app.html",
            context=_build_context(
                deps=deps,
                request=request,
                user=user,
                state=state,
                screen=screen,
                status_messages=[],
                error_message=None,
            ),
        )

    @app.post("/app/action", response_class=HTMLResponse)
    async def app_action(request: Request) -> Response:
        user = _get_user_from_session(request)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        state = _get_state_from_session(request)
        form = await request.form()
        command_name = str(form.get("command", "")).strip()
        payload_raw = str(form.get("payload_json", "{}"))
        payload = _parse_payload(payload_raw)
        if not command_name:
            return await _render_with_domain_error(
                deps=deps,
                templates=templates,
                request=request,
                user=user,
                state=state,
                error=DomainError("errors.unknown_command"),
            )
        return await _execute_and_render(
            deps=deps,
            templates=templates,
            request=request,
            user=user,
            state=state,
            command=UserCommand(name=command_name, payload=payload),
        )

    @app.post("/app/input", response_class=HTMLResponse)
    async def app_input(request: Request) -> Response:
        user = _get_user_from_session(request)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        state = _get_state_from_session(request)
        form = await request.form()
        text = str(form.get("text", ""))
        return await _execute_and_render(
            deps=deps,
            templates=templates,
            request=request,
            user=user,
            state=state,
            command=UserCommand(name="submit_text", payload={"text": text}),
        )

    @app.post("/app/upload", response_class=HTMLResponse)
    async def app_upload(request: Request, file: UploadFile) -> Response:
        user = _get_user_from_session(request)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        state = _get_state_from_session(request)
        if state.pending_input_kind != "photo_upload":
            return await _render_with_domain_error(
                deps=deps,
                templates=templates,
                request=request,
                user=user,
                state=state,
                error=DomainError("errors.send_photo_or_text"),
            )
        data = await file.read(deps.max_upload_size + 1)
        if len(data) > deps.max_upload_size:
            return await _render_with_domain_error(
                deps=deps,
                templates=templates,
                request=request,
                user=user,
                state=state,
                error=DomainError("errors.file_too_large"),
            )
        if not data:
            return await _render_with_domain_error(
                deps=deps,
                templates=templates,
                request=request,
                user=user,
                state=state,
                error=DomainError("errors.broken_image"),
            )
        deps.temp_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
        temp_path = deps.temp_dir / f"web_{uuid4().hex}{suffix}"
        try:
            async with aiofiles.open(temp_path, "wb") as temp_file:
                await temp_file.write(data)
            return await _execute_and_render(
                deps=deps,
                templates=templates,
                request=request,
                user=user,
                state=state,
                command=UserCommand(name="submit_photo_path", payload={"path": str(temp_path)}),
            )
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as error:
                logger.warning("Failed to remove temp upload file %s: %s", temp_path, error)

    return app


async def _execute_and_render(
    *,
    deps: WebDependencies,
    templates: Jinja2Templates,
    request: Request,
    user: UserProfile,
    state: WorkflowState,
    command: UserCommand,
) -> Response:
    try:
        result = await deps.facade.handle_command(user, state, command)
    except DomainError as error:
        await _log_domain_error(deps, user.id, error, command.name)
        return await _render_with_domain_error(
            deps=deps,
            templates=templates,
            request=request,
            user=user,
            state=state,
            error=error,
        )
    status_messages = await _apply_effects(deps, result.user, result.effects)
    _persist_workflow(request, result)
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context=_build_context(
            deps=deps,
            request=request,
            user=result.user,
            state=result.state,
            screen=result.screen,
            status_messages=status_messages,
            error_message=None,
        ),
    )


async def _render_with_domain_error(
    *,
    deps: WebDependencies,
    templates: Jinja2Templates,
    request: Request,
    user: UserProfile,
    state: WorkflowState,
    error: DomainError,
) -> Response:
    screen = _get_screen_from_session(request)
    if screen is None:
        fallback = await deps.facade.handle_command(user, state, UserCommand(name="open_home"))
        _persist_workflow(request, fallback)
        user = fallback.user
        state = fallback.state
        screen = fallback.screen
    error_message = deps.localizer.t(error.message_key, user.language, error.payload)
    hint = deps.localizer.t("messages.ocr_hint", user.language) if error.message_key == "errors.ocr_empty" else None
    if hint:
        error_message = f"{error_message}\n{hint}"
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context=_build_context(
            deps=deps,
            request=request,
            user=user,
            state=state,
            screen=screen,
            status_messages=[],
            error_message=error_message,
        ),
    )


async def _apply_effects(deps: WebDependencies, user: UserProfile, effects: list[Effect]) -> list[str]:
    messages: list[str] = []
    for effect in effects:
        if effect.kind == "show_status":
            message_key = str(effect.payload.get("message_key", "")).strip()
            if message_key:
                messages.append(deps.localizer.t(message_key, user.language, effect.payload))
            continue
        if effect.kind == "log_event":
            action = str(effect.payload.get("action", "")).strip()
            if action:
                payload_obj = effect.payload.get("payload")
                payload = payload_obj if isinstance(payload_obj, dict) else None
                await deps.facade.log_event(user_id=user.id, action=action, payload=payload)
    return messages


async def _log_domain_error(deps: WebDependencies, user_id: int, error: DomainError, command_name: str) -> None:
    try:
        await deps.facade.log_event(
            user_id=user_id,
            action="error_web_domain",
            payload={"error_key": error.message_key, "command": command_name},
        )
    except (RuntimeError, OSError) as log_error:
        logger.warning("Unable to log domain error event: %s", log_error)


def _build_context(
    *,
    deps: WebDependencies,
    request: Request,
    user: UserProfile,
    state: WorkflowState,
    screen: Screen,
    status_messages: list[str],
    error_message: str | None,
) -> dict[str, object]:
    language = user.language
    actions_limit = _parse_actions_limit(request.query_params.get("actions_limit"))
    visible_actions, has_more_actions, next_actions_limit = _paginate_actions(screen.actions, actions_limit)
    action_views = [_to_action_view(deps, action, language) for action in visible_actions]
    _ensure_mobile_navigation(action_views, deps, language)
    input_panel = _build_input_panel(screen.expects_input, deps, language)
    return {
        "language": language,
        "app_title": "Cashback Analyzer",
        "screen_title": deps.localizer.t(screen.title_key, language),
        "screen_body": deps.localizer.t(screen.body_key, language, screen.body_params),
        "screen_id": screen.id,
        "screen_layout_hint": screen.layout_hint,
        "status_messages": status_messages,
        "error_message": error_message,
        "actions": action_views,
        "has_more_actions": has_more_actions,
        "next_actions_limit": next_actions_limit,
        "input_panel": input_panel,
        "upload_max_bytes": deps.max_upload_size,
        "state_pending_kind": state.pending_input_kind,
        "user_name": user.full_name or user.username or str(user.external_user_id),
        "logout_label": deps.localizer.t("buttons.logout", language),
        "show_more_label": deps.localizer.t("buttons.show_more", language),
        "processing_label": deps.localizer.t("messages.processing", language),
    }


def _to_action_view(deps: WebDependencies, action: Action, language: str) -> dict[str, object]:
    variant = action.variant
    if action.destructive or action.command in {"delete_item", "request_delete_bank", "confirm_delete_bank"}:
        variant = "danger"
    elif variant == "secondary" and action.command in {"save_bank", "open_add_bank", "choose_input_method"}:
        variant = "primary"
    elif variant == "secondary" and action.command in {"open_home", "open_preview", "cancel_flow", "open_top"}:
        variant = "ghost"
    return {
        "command": action.command,
        "label": deps.localizer.t(action.label_key, language),
        "payload_json": json.dumps(_jsonify(action.payload), ensure_ascii=False),
        "variant": variant,
        "group": action.group or "default",
        "destructive": action.destructive,
    }


def _ensure_mobile_navigation(actions: list[dict[str, object]], deps: WebDependencies, language: str) -> None:
    has_safe_action = any(str(action.get("command", "")).strip() in {"open_home", "open_preview", "cancel_flow"} for action in actions)
    if not has_safe_action:
        actions.append(
            {
                "command": "open_home",
                "label": deps.localizer.t("buttons.home", language),
                "payload_json": "{}",
                "variant": "ghost",
                "group": "navigation",
                "destructive": False,
            }
        )
    has_primary = any(str(action.get("variant")) == "primary" for action in actions)
    if not has_primary:
        for action in actions:
            if str(action.get("variant")) != "danger":
                action["variant"] = "primary"
                break


def _build_input_panel(expects_input: str | None, deps: WebDependencies, language: str) -> dict[str, object] | None:
    if expects_input is None:
        return None
    if expects_input == "photo_upload":
        return {
            "kind": "file",
            "title": deps.localizer.t("labels.upload_title", language),
            "submit_label": deps.localizer.t("buttons.upload_photo", language),
            "accept": "image/*",
            "hint": deps.localizer.t("messages.upload_hint", language),
        }
    if expects_input == "manual_lines":
        return {
            "kind": "textarea",
            "title": deps.localizer.t("labels.manual_input_title", language),
            "submit_label": deps.localizer.t("buttons.send_input", language),
            "placeholder": deps.localizer.t("labels.manual_input_placeholder", language),
            "inputmode": "text",
        }
    if expects_input == "item_percent":
        return {
            "kind": "text",
            "title": deps.localizer.t("labels.percent_input_title", language),
            "submit_label": deps.localizer.t("buttons.send_input", language),
            "placeholder": deps.localizer.t("labels.percent_input_placeholder", language),
            "inputmode": "decimal",
        }
    return {
        "kind": "text",
        "title": deps.localizer.t("labels.text_input_title", language),
        "submit_label": deps.localizer.t("buttons.send_input", language),
        "placeholder": deps.localizer.t("labels.text_input_placeholder", language),
        "inputmode": "text",
    }


def _paginate_actions(actions: list[Action], limit: int) -> tuple[list[Action], bool, int]:
    if limit <= 0:
        return actions, False, limit
    if len(actions) <= limit:
        return actions, False, limit
    next_limit = limit + DEFAULT_ACTIONS_LIMIT
    return actions[:limit], True, next_limit


def _parse_actions_limit(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_ACTIONS_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_ACTIONS_LIMIT
    return max(DEFAULT_ACTIONS_LIMIT, min(value, 200))


def _parse_payload(payload_raw: str) -> dict[str, object]:
    try:
        data = json.loads(payload_raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _persist_workflow(request: Request, result: WorkflowResult) -> None:
    request.session[SESSION_USER_KEY] = _serialize_user(result.user)
    request.session[SESSION_STATE_KEY] = result.state.to_dict()
    request.session[SESSION_SCREEN_KEY] = _serialize_screen(result.screen)


def _get_user_from_session(request: Request) -> UserProfile | None:
    raw = request.session.get(SESSION_USER_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return UserProfile(
            id=int(raw["id"]),
            external_user_id=int(raw["external_user_id"]),
            username=_as_optional_str(raw.get("username")),
            full_name=_as_optional_str(raw.get("full_name")),
            language=str(raw["language"]),
            notifications_enabled=bool(raw["notifications_enabled"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _get_state_from_session(request: Request) -> WorkflowState:
    raw = request.session.get(SESSION_STATE_KEY)
    if isinstance(raw, dict):
        return WorkflowState.from_dict(raw)
    return WorkflowState()


def _get_screen_from_session(request: Request) -> Screen | None:
    raw = request.session.get(SESSION_SCREEN_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        actions_raw = raw.get("actions", [])
        actions = [
            Action(
                command=str(item.get("command", "")),
                label_key=str(item.get("label_key", "")),
                payload=item.get("payload", {}) if isinstance(item.get("payload"), dict) else {},
                destructive=bool(item.get("destructive", False)),
                variant=str(item.get("variant", "secondary")),
                group=_as_optional_str(item.get("group")),
            )
            for item in actions_raw
            if isinstance(item, dict)
        ]
        return Screen(
            id=str(raw.get("id", "home")),
            title_key=str(raw.get("title_key", "screens.home")),
            body_key=str(raw.get("body_key", "screens.home")),
            body_params=raw.get("body_params", {}) if isinstance(raw.get("body_params"), dict) else {},
            actions=actions,
            expects_input=_as_optional_str(raw.get("expects_input")),
            layout_hint=str(raw.get("layout_hint", "default")),
        )
    except (ValueError, TypeError):
        return None


def _serialize_user(user: UserProfile) -> dict[str, object]:
    return {
        "id": user.id,
        "external_user_id": user.external_user_id,
        "username": user.username,
        "full_name": user.full_name,
        "language": user.language,
        "notifications_enabled": user.notifications_enabled,
    }


def _serialize_screen(screen: Screen) -> dict[str, object]:
    return {
        "id": screen.id,
        "title_key": screen.title_key,
        "body_key": screen.body_key,
        "body_params": _jsonify(screen.body_params),
        "actions": [
            {
                "command": action.command,
                "label_key": action.label_key,
                "payload": _jsonify(action.payload),
                "destructive": action.destructive,
                "variant": action.variant,
                "group": action.group,
            }
            for action in screen.actions
        ],
        "expects_input": screen.expects_input,
        "layout_hint": screen.layout_hint,
    }


def _jsonify(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    return value


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
