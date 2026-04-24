from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.web.app import WebDependencies, create_web_app
from app.i18n.localizer import Localizer


@pytest.fixture()
def localizer() -> Localizer:
    locales_dir = Path(__file__).resolve().parents[1] / "app" / "locales"
    return Localizer(locales_dir=locales_dir, default_language="ru")


def _make_deps(
    *,
    localizer: Localizer,
    webhook_secret: str = "",
    bot: object | None = None,
    dispatcher: object | None = None,
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
        webhook_path="/bot/webhook",
        webhook_secret=webhook_secret,
        bot=bot,
        dispatcher=dispatcher,
    )


@pytest.mark.asyncio
async def test_webhook_requires_valid_secret(localizer: Localizer) -> None:
    deps = _make_deps(localizer=localizer, webhook_secret="s3cret")
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/bot/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            json={},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_webhook_rejects_missing_secret_header(localizer: Localizer) -> None:
    deps = _make_deps(localizer=localizer, webhook_secret="s3cret")
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/bot/webhook", json={})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_webhook_accepts_valid_secret_and_dispatches(localizer: Localizer) -> None:
    # Dispatcher.feed_webhook_update is awaited; bot is passed through.
    bot = MagicMock()
    dispatcher = MagicMock()
    dispatcher.feed_webhook_update = AsyncMock()
    deps = _make_deps(
        localizer=localizer,
        webhook_secret="s3cret",
        bot=bot,
        dispatcher=dispatcher,
    )
    app = create_web_app(deps)
    from unittest.mock import patch

    fake_update = MagicMock()
    with patch("aiogram.types.Update.model_validate", return_value=fake_update) as validate:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/bot/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
                json={"update_id": 1},
            )
    assert res.status_code == 200
    validate.assert_called_once()
    dispatcher.feed_webhook_update.assert_awaited_once_with(bot, fake_update)


@pytest.mark.asyncio
async def test_webhook_without_secret_bypasses_check(localizer: Localizer) -> None:
    bot = MagicMock()
    dispatcher = MagicMock()
    dispatcher.feed_webhook_update = AsyncMock()
    deps = _make_deps(localizer=localizer, webhook_secret="", bot=bot, dispatcher=dispatcher)
    app = create_web_app(deps)
    from unittest.mock import patch

    with patch("aiogram.types.Update.model_validate", return_value=MagicMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/bot/webhook", json={"update_id": 1})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_webhook_returns_503_when_dispatcher_missing(localizer: Localizer) -> None:
    deps = _make_deps(localizer=localizer, webhook_secret="", bot=None, dispatcher=None)
    app = create_web_app(deps)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/bot/webhook", json={})
    assert res.status_code == 503
