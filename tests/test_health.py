from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.web.app import WebDependencies, create_web_app
from app.i18n.localizer import Localizer


@pytest.fixture
def localizer() -> Localizer:
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    return Localizer(locales_dir=locales_dir, default_language="ru")


def _make_deps(
    *,
    localizer: Localizer,
    db_ping=None,
    telegram_ping=None,
    metrics_token: str = "",
    app_version: str = "v0.1.0",
) -> WebDependencies:
    return WebDependencies(
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
        db_ping=db_ping,
        telegram_ping=telegram_ping,
        ocr_provider_name="tesseract",
        app_version=app_version,
        metrics_token=metrics_token,
    )


@pytest.mark.asyncio
async def test_health_returns_ok_when_all_pings_succeed(localizer: Localizer) -> None:
    deps = _make_deps(
        localizer=localizer,
        db_ping=AsyncMock(return_value=None),
        telegram_ping=AsyncMock(return_value=None),
        app_version="abc1234",
    )
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["telegram"] == "ok"
    assert body["ocr"]["primary"] == "tesseract"
    assert body["version"] == "abc1234"


@pytest.mark.asyncio
async def test_health_degraded_when_db_fails(localizer: Localizer) -> None:
    async def failing_ping() -> None:
        raise RuntimeError("db down")

    deps = _make_deps(
        localizer=localizer,
        db_ping=failing_ping,
        telegram_ping=AsyncMock(return_value=None),
    )
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"


@pytest.mark.asyncio
async def test_health_reports_na_without_pings(localizer: Localizer) -> None:
    deps = _make_deps(localizer=localizer)
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/health")
    # No db_ping/telegram_ping registered — both are n/a and status is ok.
    assert res.status_code == 200
    body = res.json()
    assert body["db"] == "n/a"
    assert body["telegram"] == "n/a"


@pytest.mark.asyncio
async def test_metrics_requires_token_when_set(localizer: Localizer) -> None:
    deps = _make_deps(localizer=localizer, metrics_token="supersecret")
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_no = await client.get("/metrics")
        res_wrong = await client.get("/metrics", headers={"Authorization": "Bearer nope"})
        res_ok = await client.get("/metrics", headers={"Authorization": "Bearer supersecret"})
    assert res_no.status_code == 401
    assert res_wrong.status_code == 401
    assert res_ok.status_code == 200
    assert b"cashback_bot_requests_total" in res_ok.content


@pytest.mark.asyncio
async def test_metrics_open_when_no_token_set(localizer: Localizer) -> None:
    deps = _make_deps(localizer=localizer, metrics_token="")
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/metrics")
    assert res.status_code == 200
