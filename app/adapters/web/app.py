from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.adapters.auth_telegram import verify_telegram_login
from app.application import ApplicationFacade
from app.application.auth.models import LocalAuthenticationCommand, LocalRegistrationCommand
from app.application.dto.media import ImageUpload
from app.application.models import Action, Effect, Screen, UserCommand, WorkflowResult, WorkflowState
from app.domain.errors import DomainError
from app.domain.models import UserAccount, UserIdentity
from app.i18n.localizer import Localizer

logger = logging.getLogger(__name__)

SESSION_USER_ID_KEY = "web_user_id"
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
    telegram_auth_enabled: bool
    web_base_url: str
    max_upload_size: int
    secure_cookies: bool
    session_secret: str
    # Webhook integration (aiogram Dispatcher/Bot are injected from runtime).
    webhook_path: str = "/bot/webhook"
    webhook_secret: str = ""
    # Any aiogram Bot; typed loosely so tests don't need the full Bot surface.
    bot: Any | None = None
    dispatcher: Any | None = None
    # Security / observability — `*` allows any origin (dev default). Production
    # callers should set an explicit list via CORS_ORIGINS.
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    metrics_token: str = ""
    api_rate_limit_per_minute: int = 60
    # Optional health-check helpers — the runtime wires ping callables so the
    # web app can verify DB and Telegram reachability without holding
    # references to the engine/bot objects itself.
    db_ping: Any | None = None
    telegram_ping: Any | None = None
    ocr_provider_name: str = "auto"
    app_version: str = "dev"


def create_web_app(deps: WebDependencies) -> FastAPI:
    app = FastAPI(title="Cashback Analyzer Web", docs_url=None, redoc_url=None)
    app.state.deps = deps
    # Expose Prometheus counters on the app so the router-side LoggingMiddleware
    # and OCR adapters can increment them without a module-level global.
    app.state.metrics = _build_metrics_registry()
    app.add_middleware(_SecurityHeadersMiddleware)
    app.add_middleware(_CorrelationIdMiddleware)
    app.add_middleware(_RateLimitMiddleware, deps=deps)
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=deps.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
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
        user = await _get_current_user(request, deps)
        if user is not None:
            return RedirectResponse(url="/app", status_code=303)
        return _render_landing(request, deps, templates)

    @app.post("/auth/register")
    async def register(request: Request) -> Response:
        form = await request.form()
        try:
            user = await deps.facade.register_local_user(
                LocalRegistrationCommand(
                    username=str(form.get("username", "")),
                    password=str(form.get("password", "")),
                    display_name=_clean_optional(form.get("display_name")),
                    email=_clean_optional(form.get("email")),
                )
            )
        except DomainError as error:
            return _render_landing(request, deps, templates, error=error, status_code=400)
        request.session.clear()
        _persist_authenticated_user(request, user.id)
        return RedirectResponse(url="/app", status_code=303)

    @app.post("/auth/login")
    async def login(request: Request) -> Response:
        form = await request.form()
        try:
            user = await deps.facade.authenticate_local_user(
                LocalAuthenticationCommand(
                    username=str(form.get("username", "")),
                    password=str(form.get("password", "")),
                )
            )
        except DomainError as error:
            return _render_landing(request, deps, templates, error=error, status_code=401)
        request.session.clear()
        _persist_authenticated_user(request, user.id)
        return RedirectResponse(url="/app", status_code=303)

    @app.get("/auth/telegram/callback")
    async def telegram_callback(request: Request) -> Response:
        if not deps.telegram_auth_enabled:
            return RedirectResponse(url="/", status_code=303)
        try:
            identity = verify_telegram_login(
                {key: value for key, value in request.query_params.items()},
                bot_token=deps.bot_token,
            )
            current_user = await _get_current_user(request, deps)
            if current_user is None:
                user = await deps.facade.authenticate_external_identity(
                    identity,
                    create_user_if_missing=False,
                    log_action="web_telegram_login",
                )
                request.session.clear()
                _persist_authenticated_user(request, user.id)
            else:
                await deps.facade.link_external_identity(user_id=current_user.id, identity=identity)
            return RedirectResponse(url="/app", status_code=303)
        except DomainError as error:
            return _render_landing(request, deps, templates, error=error, status_code=401)

    @app.post("/auth/telegram/unlink")
    async def unlink_telegram(request: Request) -> Response:
        user = await _get_current_user(request, deps)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        try:
            await deps.facade.unlink_external_identity(user_id=user.id, provider="telegram")
        except DomainError as error:
            return await _render_with_domain_error(
                deps=deps,
                templates=templates,
                request=request,
                user=user,
                state=_get_state_from_session(request),
                error=error,
            )
        return RedirectResponse(url="/app", status_code=303)

    @app.post("/auth/logout")
    async def logout(request: Request) -> Response:
        request.session.clear()
        return RedirectResponse(url="/", status_code=303)

    @app.get("/app", response_class=HTMLResponse)
    async def app_home(request: Request) -> Response:
        user = await _get_current_user(request, deps)
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
        identities = await deps.facade.list_external_identities(user_id=user.id)
        return templates.TemplateResponse(
            request=request,
            name="app.html",
            context=_build_context(
                deps=deps,
                request=request,
                user=user,
                state=state,
                screen=screen,
                identities=identities,
                status_messages=[],
                error_message=None,
            ),
        )

    @app.post("/app/action", response_class=HTMLResponse)
    async def app_action(request: Request) -> Response:
        user = await _get_current_user(request, deps)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        state = _get_state_from_session(request)
        form = await request.form()
        command_name = str(form.get("command", "")).strip()
        payload = _parse_payload(str(form.get("payload_json", "{}")))
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
        user = await _get_current_user(request, deps)
        if user is None:
            return RedirectResponse(url="/", status_code=303)
        state = _get_state_from_session(request)
        form = await request.form()
        return await _execute_and_render(
            deps=deps,
            templates=templates,
            request=request,
            user=user,
            state=state,
            command=UserCommand(name="submit_text", payload={"text": str(form.get("text", ""))}),
        )

    @app.post("/app/upload", response_class=HTMLResponse)
    async def app_upload(request: Request, file: UploadFile) -> Response:
        user = await _get_current_user(request, deps)
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
        return await _execute_and_render(
            deps=deps,
            templates=templates,
            request=request,
            user=user,
            state=state,
            command=UserCommand(
                name="submit_uploaded_image",
                payload={
                    "upload": ImageUpload(
                        content=data,
                        filename=file.filename or "upload.jpg",
                        content_type=file.content_type or "image/jpeg",
                    )
                },
            ),
        )

    @app.get("/health")
    async def health(request: Request) -> Response:
        """Deep health probe — touches DB and optionally Telegram / OCR so
        load balancers and orchestrators only route traffic to ready replicas.
        Returns HTTP 503 when any dependency is unreachable; 200 otherwise."""
        _ = request
        db_status = await _check_db(deps)
        telegram_status = await _check_telegram(deps)
        ocr_status = deps.ocr_provider_name or "n/a"
        # "n/a" means the probe isn't wired (e.g. web-only deployment without
        # a bot handle), not that the subsystem is down. Only treat "error"
        # as an actual degradation signal.
        degraded = db_status == "error" or telegram_status == "error"
        payload = {
            "status": "ok" if not degraded else "degraded",
            "db": db_status,
            "telegram": telegram_status,
            "ocr": {"primary": ocr_status, "status": "ok"},
            "version": deps.app_version,
        }
        code = 200 if not degraded else 503
        return JSONResponse(content=payload, status_code=code)

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        """Prometheus scrape endpoint. Protected by a bearer token when
        ``METRICS_TOKEN`` is set — a missing/wrong token returns 401. An empty
        token means the endpoint is exposed to anyone that can reach the web
        listener (fine for local dev; don't do this in production)."""
        if deps.metrics_token:
            auth_header = request.headers.get("authorization", "")
            expected = f"Bearer {deps.metrics_token}"
            if auth_header != expected:
                return Response(status_code=401, content="unauthorized")
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        data = generate_latest(app.state.metrics.registry)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    @app.post(deps.webhook_path)
    async def telegram_webhook(request: Request) -> Response:
        """Telegram webhook receiver.

        Validates ``X-Telegram-Bot-Api-Secret-Token`` when ``WEBHOOK_SECRET`` is
        set. The bot/dispatcher are optional so tests can assert the security
        check without wiring a full aiogram stack.
        """
        if deps.webhook_secret:
            token = request.headers.get("x-telegram-bot-api-secret-token", "")
            if token != deps.webhook_secret:
                return Response(status_code=403, content="forbidden")
        if deps.bot is None or deps.dispatcher is None:
            return Response(status_code=503, content="webhook not wired")
        try:
            payload = await request.json()
        except Exception:
            return Response(status_code=400, content="invalid json")
        try:
            # Lazy import so the web package stays importable without aiogram
            # (tests that only hit /health or /metrics don't need it).
            from aiogram.types import Update

            update = Update.model_validate(payload, context={"bot": deps.bot})
            await deps.dispatcher.feed_webhook_update(deps.bot, update)
        except Exception as error:  # pragma: no cover - logged for ops
            logger.exception("Webhook processing failed: %s", error)
            return Response(status_code=500, content="processing error")
        return Response(status_code=200, content="ok")

    @app.get("/api/best")
    async def api_best(request: Request, q: str = "") -> Response:
        """Feature-parity with Telegram inline mode: ``GET /api/best?q=азс``
        returns the signed-in user's best-matching card plus fallback top
        categories. No FSM, no HTML — usable from a future mobile app, a
        browser extension, or a scripted shell pipeline."""
        user = await _get_current_user(request, deps)
        if user is None:
            return JSONResponse(status_code=401, content={"error": "unauthenticated"})
        snapshot = await deps.facade.ranking_snapshot(
            user_id=user.id, query=q, language=user.language
        )
        return JSONResponse(
            content={
                "query": snapshot.query,
                "normalized_slug": snapshot.normalized_slug,
                "display_name": snapshot.display_name,
                "best_match": _leader_to_dict(snapshot.best_match),
                "leaders": [_leader_to_dict(leader) for leader in snapshot.leaders],
            }
        )

    return app


def _leader_to_dict(leader) -> dict[str, object] | None:
    if leader is None:
        return None
    return {
        "category_slug": leader.category_slug,
        "category_name": leader.category_name,
        "best_percent": str(leader.best_percent),
        "bank_names": leader.bank_names,
    }


async def _execute_and_render(
    *,
    deps: WebDependencies,
    templates: Jinja2Templates,
    request: Request,
    user: UserAccount,
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
    identities = await deps.facade.list_external_identities(user_id=result.user.id)
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context=_build_context(
            deps=deps,
            request=request,
            user=result.user,
            state=result.state,
            screen=result.screen,
            identities=identities,
            status_messages=status_messages,
            error_message=None,
        ),
    )


async def _render_with_domain_error(
    *,
    deps: WebDependencies,
    templates: Jinja2Templates,
    request: Request,
    user: UserAccount,
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
    if error.message_key == "errors.ocr_empty":
        error_message = f"{error_message}\n{deps.localizer.t('messages.ocr_hint', user.language)}"
    identities = await deps.facade.list_external_identities(user_id=user.id)
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context=_build_context(
            deps=deps,
            request=request,
            user=user,
            state=state,
            screen=screen,
            identities=identities,
            status_messages=[],
            error_message=error_message,
        ),
    )


async def _apply_effects(deps: WebDependencies, user: UserAccount, effects: list[Effect]) -> list[str]:
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
    user: UserAccount,
    state: WorkflowState,
    screen: Screen,
    identities: list[UserIdentity],
    status_messages: list[str],
    error_message: str | None,
) -> dict[str, object]:
    language = user.language
    actions_limit = _parse_actions_limit(request.query_params.get("actions_limit"))
    visible_actions, has_more_actions, next_actions_limit = _paginate_actions(screen.actions, actions_limit)
    action_views = [_to_action_view(deps, action, language) for action in visible_actions]
    _ensure_mobile_navigation(action_views, deps, language)
    telegram_linked = any(identity.provider == "telegram" for identity in identities)
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
        "input_panel": _build_input_panel(screen.expects_input, deps, language),
        "upload_max_bytes": deps.max_upload_size,
        "state_pending_kind": state.pending_input_kind,
        "user_name": user.display_name,
        "logout_label": deps.localizer.t("buttons.logout", language),
        "show_more_label": deps.localizer.t("buttons.show_more", language),
        "processing_label": deps.localizer.t("messages.processing", language),
        "telegram_enabled": deps.telegram_auth_enabled,
        "telegram_linked": telegram_linked,
        "telegram_auth_url": _telegram_callback_url(deps),
        "bot_username": deps.bot_username,
        "linked_accounts_label": deps.localizer.t("labels.linked_accounts", language),
        "telegram_linked_label": deps.localizer.t("labels.telegram_linked", language),
        "telegram_unlinked_label": deps.localizer.t("labels.telegram_unlinked", language),
        "link_telegram_label": deps.localizer.t("buttons.link_telegram", language),
        "unlink_telegram_label": deps.localizer.t("buttons.unlink_telegram", language),
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
    return actions[:limit], True, limit + DEFAULT_ACTIONS_LIMIT


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
    return data if isinstance(data, dict) else {}


def _persist_workflow(request: Request, result: WorkflowResult) -> None:
    _persist_authenticated_user(request, result.user.id)
    request.session[SESSION_STATE_KEY] = result.state.to_dict()
    request.session[SESSION_SCREEN_KEY] = _serialize_screen(result.screen)


async def _get_current_user(request: Request, deps: WebDependencies) -> UserAccount | None:
    user_id = _get_user_id_from_session(request)
    if user_id is None:
        return None
    user = await deps.facade.get_user(user_id)
    if user is None:
        request.session.clear()
        return None
    return user


def _persist_authenticated_user(request: Request, user_id: int) -> None:
    request.session[SESSION_USER_ID_KEY] = user_id


def _get_user_id_from_session(request: Request) -> int | None:
    raw = request.session.get(SESSION_USER_ID_KEY)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _get_state_from_session(request: Request) -> WorkflowState:
    raw = request.session.get(SESSION_STATE_KEY)
    return WorkflowState.from_dict(raw) if isinstance(raw, dict) else WorkflowState()


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


def _render_landing(
    request: Request,
    deps: WebDependencies,
    templates: Jinja2Templates,
    *,
    error: DomainError | None = None,
    status_code: int = 200,
) -> Response:
    language = deps.default_language
    context: dict[str, object] = {
        "language": language,
        "title": "Cashback Analyzer",
        "subtitle": deps.localizer.t("messages.web_auth_hint", language),
        "telegram_enabled": deps.telegram_auth_enabled,
        "bot_username": deps.bot_username,
        "auth_url": _telegram_callback_url(deps),
    }
    if error is not None:
        context["error_message"] = deps.localizer.t(error.message_key, language, error.payload)
    return templates.TemplateResponse(request=request, name="landing.html", context=context, status_code=status_code)


def _telegram_callback_url(deps: WebDependencies) -> str:
    return f"{deps.web_base_url.rstrip('/')}/auth/telegram/callback"


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


# --------------------------------------------------------------------------
# Middleware / observability helpers
# --------------------------------------------------------------------------

class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds baseline security headers. These are cheap in response time and
    prevent entire classes of UI vulnerabilities (clickjacking,
    content-type sniffing) even on otherwise correct applications."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


class _CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Sets ``correlation_id_var`` from the X-Request-Id header (or a fresh
    uuid4 if missing) so every log line emitted during a request shares
    the same trace token. The chosen id is echoed back on the response."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        import uuid

        from app.bootstrap.correlation import correlation_id_var

        cid = (request.headers.get("x-request-id") or "").strip() or str(uuid.uuid4())[:8]
        token = correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers.setdefault("X-Request-Id", cid)
        return response


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token-bucket limiter for public JSON API endpoints. We only apply
    it to /api/* so that webhooks, health, and the HTML app (which already has
    session auth) are unaffected. The bucket is in-memory, single-process; if
    you run multiple web replicas put a real rate limiter at the edge."""

    def __init__(self, app, deps: WebDependencies) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._deps = deps
        # Token bucket parameters: allow the configured per-minute budget with
        # burst up to the same value; refill monotonically.
        from app.adapters.rate_limit import TokenBucketRateLimiter

        rpm = max(1, int(deps.api_rate_limit_per_minute))
        self._limiter = TokenBucketRateLimiter(
            capacity=rpm,
            refill_per_second=rpm / 60.0,
        )

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        client = request.client
        key_value = 0
        if client is not None and client.host:
            key_value = _stable_ip_key(client.host)
        if not self._limiter.allow(key_value):
            return JSONResponse(status_code=429, content={"error": "rate_limited"})
        return await call_next(request)


def _stable_ip_key(host: str) -> int:
    # TokenBucket stores buckets keyed by int. We hash the IP into a stable
    # unsigned 62-bit integer so the same IP always hits the same bucket.
    import hashlib

    digest = hashlib.sha1(host.encode("utf-8"), usedforsecurity=False).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 62) - 1)


class _MetricsRegistry:
    """Thin wrapper around prometheus_client collectors used by LoggingMiddleware
    and OCR adapters to update counters without importing prometheus_client
    at every call site."""

    def __init__(self) -> None:
        from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

        self.registry = CollectorRegistry(auto_describe=True)
        self.requests_total = Counter(
            "cashback_bot_requests_total",
            "Handler invocations by handler and status",
            ["handler", "status"],
            registry=self.registry,
        )
        self.request_duration = Histogram(
            "cashback_bot_request_duration_seconds",
            "Handler latency distribution",
            ["handler"],
            registry=self.registry,
        )
        self.ocr_calls_total = Counter(
            "cashback_bot_ocr_calls_total",
            "OCR calls by provider and result",
            ["provider", "result"],
            registry=self.registry,
        )
        self.active_users = Gauge(
            "cashback_bot_active_users_total",
            "Unique users seen in the current process window",
            registry=self.registry,
        )
        self._seen_users: set[int] = set()

    def observe_user(self, user_id: int) -> None:
        if user_id in self._seen_users:
            return
        self._seen_users.add(user_id)
        self.active_users.set(len(self._seen_users))


def _build_metrics_registry() -> _MetricsRegistry:
    return _MetricsRegistry()


async def _check_db(deps: WebDependencies) -> str:
    ping = deps.db_ping
    if ping is None:
        return "n/a"
    import asyncio

    try:
        result = ping()
        if asyncio.iscoroutine(result):
            await asyncio.wait_for(result, timeout=2.0)
        return "ok"
    except Exception as error:
        logger.warning("Health DB ping failed: %s", error)
        return "error"


async def _check_telegram(deps: WebDependencies) -> str:
    ping = deps.telegram_ping
    if ping is None:
        return "n/a"
    import asyncio

    try:
        result = ping()
        if asyncio.iscoroutine(result):
            await asyncio.wait_for(result, timeout=3.0)
        return "ok"
    except Exception as error:
        logger.warning("Health Telegram ping failed: %s", error)
        return "error"
