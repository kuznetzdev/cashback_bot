from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from aiogram.fsm.storage.memory import MemoryStorage

from app.bootstrap.config import Settings
from app.bootstrap.runtime import build_fsm_storage


def _make_settings(**overrides: object) -> Settings:
    base = {
        "BOT_TOKEN": "123456:TEST_TOKEN",
        "TELEGRAM_BOT_USERNAME": "bot",
        "APP_ENABLE_TELEGRAM": "true",
        "APP_ENABLE_WEB": "false",
        "WEB_SESSION_SECRET": "secret-strong-value",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return Settings(**base)  # type: ignore[arg-type]


def test_build_fsm_storage_defaults_to_memory() -> None:
    settings = _make_settings()
    storage = build_fsm_storage(settings)
    assert isinstance(storage, MemoryStorage)


def test_build_fsm_storage_memory_explicit() -> None:
    settings = _make_settings(FSM_STORAGE="memory", REDIS_URL="redis://cache:6379/0")
    storage = build_fsm_storage(settings)
    # Even if REDIS_URL is set, FSM_STORAGE=memory wins.
    assert isinstance(storage, MemoryStorage)


def test_build_fsm_storage_redis_without_url_falls_back_to_memory(caplog) -> None:
    settings = _make_settings(FSM_STORAGE="redis", REDIS_URL="")
    with caplog.at_level("WARNING"):
        storage = build_fsm_storage(settings)
    assert isinstance(storage, MemoryStorage)
    assert any("FSM_STORAGE=redis" in rec.message for rec in caplog.records)


def test_build_fsm_storage_redis_with_url_uses_redis_storage() -> None:
    settings = _make_settings(FSM_STORAGE="redis", REDIS_URL="redis://cache:6379/0")
    fake_storage = MagicMock()
    fake_cls = MagicMock()
    fake_cls.from_url.return_value = fake_storage
    with patch("aiogram.fsm.storage.redis.RedisStorage", fake_cls):
        storage = build_fsm_storage(settings)
    assert storage is fake_storage
    fake_cls.from_url.assert_called_once_with(
        "redis://cache:6379/0", key_prefix="cashback_fsm:"
    )


def test_settings_rejects_unknown_fsm_storage_value() -> None:
    with pytest.raises(ValueError):
        _make_settings(FSM_STORAGE="mongodb")
