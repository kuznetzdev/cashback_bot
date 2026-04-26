"""Regression tests for the production-hardening pass: inline handler
resilience, rate-limiter eviction, OCR temp-dir sweep, OpenAI client close,
and config fail-fast validation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.telegram.inline import InlineDependencies, handle_inline_query
from app.adapters.telegram.rate_limit import TokenBucketRateLimiter
from app.bootstrap.config import Settings
from app.bootstrap.runtime import _validate_startup_settings
from app.i18n.localizer import Localizer

LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "locales"


def _localizer() -> Localizer:
    return Localizer(locales_dir=LOCALES_DIR, default_language="ru")


def _fake_query(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        query=text,
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_inline_returns_empty_on_facade_failure() -> None:
    # If DB is down and facade raises, Telegram should see an empty inline
    # answer — not a hung coroutine or an exception bubbling out.
    facade = SimpleNamespace(
        find_user_by_external_identity=AsyncMock(side_effect=RuntimeError("DB down")),
        ranking_snapshot=AsyncMock(),
    )
    deps = InlineDependencies(
        facade=facade,
        localizer=_localizer(),
        default_language="ru",
        bot_username="cashback_bot",
    )
    query = _fake_query("азс")

    await handle_inline_query(query, deps)

    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs["results"] == []


@pytest.mark.asyncio
async def test_inline_returns_empty_on_snapshot_failure() -> None:
    facade = SimpleNamespace(
        find_user_by_external_identity=AsyncMock(
            return_value=SimpleNamespace(id=1, language="ru", display_name="U")
        ),
        ranking_snapshot=AsyncMock(side_effect=RuntimeError("snapshot blew up")),
    )
    deps = InlineDependencies(
        facade=facade,
        localizer=_localizer(),
        default_language="ru",
        bot_username="cashback_bot",
    )
    query = _fake_query("азс")

    await handle_inline_query(query, deps)

    assert query.answer.await_args.kwargs["results"] == []


def test_rate_limiter_evicts_idle_buckets() -> None:
    # With sweep_every=1, every allow() call triggers a sweep; idle_ttl=10
    # means buckets older than 10 seconds get removed.
    limiter = TokenBucketRateLimiter(
        capacity=3,
        refill_per_second=1.0,
        idle_ttl_seconds=10.0,
        sweep_every=1,
    )
    # Ten users each burn one token at t=0 — 10 buckets tracked.
    for uid in range(10):
        limiter.allow(user_id=uid, now=0.0)
    assert limiter.tracked_users() == 10

    # Fast-forward 100 seconds. User 999 pings in — sweep fires, everyone else
    # should be evicted as idle.
    limiter.allow(user_id=999, now=100.0)
    assert limiter.tracked_users() == 1


def test_rate_limiter_does_not_evict_recently_active_users() -> None:
    limiter = TokenBucketRateLimiter(
        capacity=3,
        refill_per_second=1.0,
        idle_ttl_seconds=10.0,
        sweep_every=1,
    )
    limiter.allow(user_id=1, now=0.0)
    # User 2 pings after user 1 is stale (t=20), but user 1's bucket was
    # touched less than 10s ago relative to the sweep — still gone.
    limiter.allow(user_id=2, now=20.0)
    assert limiter.tracked_users() == 1
    # Both users active within TTL — both preserved.
    limiter.allow(user_id=1, now=21.0)
    limiter.allow(user_id=2, now=22.0)
    assert limiter.tracked_users() == 2


def test_rate_limiter_validates_idle_ttl() -> None:
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=1, refill_per_second=1.0, idle_ttl_seconds=0)
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=1, refill_per_second=1.0, idle_ttl_seconds=-5)


def test_tesseract_adapter_sweeps_stale_temp_files_on_startup(tmp_path: Path) -> None:
    from app.adapters.ocr_tesseract import TesseractOCRAdapter

    temp_dir = tmp_path / "ocr"
    temp_dir.mkdir()
    stale_a = temp_dir / "stale_a.png"
    stale_b = temp_dir / "stale_b.png"
    non_png = temp_dir / "not_ours.txt"
    stale_a.write_bytes(b"x")
    stale_b.write_bytes(b"y")
    non_png.write_text("keep me")

    TesseractOCRAdapter(
        tesseract_path="/usr/bin/tesseract",
        timeout=30,
        max_file_size=1024 * 1024,
        temp_dir=temp_dir,
    )

    assert not stale_a.exists()
    assert not stale_b.exists()
    # Non-PNG files are left alone — the sweep is intentionally scoped.
    assert non_png.exists()


def test_config_fails_fast_when_openai_provider_missing_key() -> None:
    settings = Settings(
        BOT_TOKEN="123456:valid_token",
        APP_ENABLE_TELEGRAM=True,
        APP_ENABLE_WEB=False,
        OCR_PROVIDER="openai",
        OPENAI_API_KEY="",
    )
    with pytest.raises(RuntimeError) as error:
        _validate_startup_settings(settings)
    assert "OPENAI_API_KEY" in str(error.value)


def test_config_accepts_auto_provider_without_key() -> None:
    # auto degrades to Tesseract when the key is absent — this is fine.
    settings = Settings(
        BOT_TOKEN="123456:valid_token",
        APP_ENABLE_TELEGRAM=True,
        APP_ENABLE_WEB=False,
        OCR_PROVIDER="auto",
        OPENAI_API_KEY="",
    )
    _validate_startup_settings(settings)  # must not raise


@pytest.mark.asyncio
async def test_openai_vision_adapter_exposes_close() -> None:
    from app.adapters.ocr_openai_vision import OpenAIVisionOCRAdapter

    adapter = OpenAIVisionOCRAdapter(api_key="sk-test-123", model="gpt-4o-mini")
    # close() must exist and be safe to await twice (the AsyncOpenAI client
    # tolerates repeated close() as of openai>=1.0).
    await adapter.close()
    await adapter.close()
