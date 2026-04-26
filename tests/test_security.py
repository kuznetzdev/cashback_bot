from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.web.app import WebDependencies, create_web_app
from app.bootstrap.config import Settings
from app.i18n.localizer import Localizer


@pytest.fixture
def localizer() -> Localizer:
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    return Localizer(locales_dir=locales_dir, default_language="ru")


def _base_deps(localizer: Localizer, **overrides) -> WebDependencies:
    base = dict(
        facade=MagicMock(),
        localizer=localizer,
        default_language="ru",
        temp_dir=Path("."),
        bot_token="test",
        bot_username="bot",
        telegram_auth_enabled=False,
        web_base_url="http://localhost:8080",
        max_upload_size=1024,
        secure_cookies=False,
        session_secret="x" * 32,
    )
    base.update(overrides)
    return WebDependencies(**base)


# --- Settings validation ---------------------------------------------------


def test_settings_rejects_default_session_secret_when_web_enabled() -> None:
    with pytest.raises(ValueError, match="WEB_SESSION_SECRET"):
        Settings(
            BOT_TOKEN="123456:valid",
            TELEGRAM_BOT_USERNAME="bot",
            APP_ENABLE_TELEGRAM=False,
            APP_ENABLE_WEB=True,
            WEB_SESSION_SECRET="change-me-session-secret",
        )


def test_settings_accepts_default_session_secret_when_web_disabled() -> None:
    # Bot-only deployments don't need a strong session secret.
    settings = Settings(
        BOT_TOKEN="123456:valid",
        APP_ENABLE_TELEGRAM=True,
        APP_ENABLE_WEB=False,
        WEB_SESSION_SECRET="change-me-session-secret",
    )
    assert settings.web_session_secret == "change-me-session-secret"


def test_settings_accepts_strong_session_secret_when_web_enabled() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid",
        TELEGRAM_BOT_USERNAME="bot",
        APP_ENABLE_TELEGRAM=False,
        APP_ENABLE_WEB=True,
        WEB_SESSION_SECRET="a-strong-random-secret-abc1234",
    )
    assert settings.web_session_secret.startswith("a-strong")


# --- /metrics access control ----------------------------------------------


@pytest.mark.asyncio
async def test_metrics_rejects_missing_token(localizer: Localizer) -> None:
    deps = _base_deps(localizer, metrics_token="secret-value")
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/metrics")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_metrics_rejects_wrong_token(localizer: Localizer) -> None:
    deps = _base_deps(localizer, metrics_token="secret-value")
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


# --- /api/best auth --------------------------------------------------------


@pytest.mark.asyncio
async def test_api_best_requires_authentication(localizer: Localizer) -> None:
    deps = _base_deps(localizer)
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/best?q=test")
    assert res.status_code == 401
    assert res.json() == {"error": "unauthenticated"}


# --- Security headers & CORS ----------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_present_on_every_response(localizer: Localizer) -> None:
    deps = _base_deps(localizer)
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "no-referrer"


@pytest.mark.asyncio
async def test_correlation_id_is_echoed_back(localizer: Localizer) -> None:
    deps = _base_deps(localizer)
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health", headers={"X-Request-Id": "trace-9999"})
    assert res.headers.get("X-Request-Id") == "trace-9999"


# --- Rate limiting on /api/* ----------------------------------------------


@pytest.mark.asyncio
async def test_api_rate_limit_blocks_after_budget_exhausted(localizer: Localizer) -> None:
    # Tiny budget so we can exhaust it within the test.
    deps = _base_deps(localizer, api_rate_limit_per_minute=3)
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        codes = []
        for _ in range(5):
            r = await client.get("/api/best?q=x")
            codes.append(r.status_code)
    # First 3 responses can still be 401 (no session), but once the bucket
    # empties we should see at least one 429.
    assert 429 in codes, f"expected 429 in codes, got {codes}"
