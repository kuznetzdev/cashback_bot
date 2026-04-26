from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.storage.base import StorageKey

from app.adapters.circuit_breaker import CircuitBreaker
from app.adapters.telegram.resilient_storage import ResilientFSMStorage


def _key(user_id: int = 42) -> StorageKey:
    return StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)


@pytest.mark.asyncio
async def test_resilient_storage_uses_primary_when_healthy() -> None:
    primary = MagicMock()
    primary.get_state = AsyncMock(return_value="some_state")
    primary.set_state = AsyncMock()
    primary.set_data = AsyncMock()
    primary.get_data = AsyncMock(return_value={"k": "v"})
    primary.close = AsyncMock()

    fallback = MagicMock()
    fallback.close = AsyncMock()
    storage = ResilientFSMStorage(primary, fallback=fallback)

    state = await storage.get_state(_key())
    assert state == "some_state"
    await storage.set_state(_key(), "new_state")
    primary.set_state.assert_awaited_once()
    # Fallback should not have been touched.
    assert not getattr(fallback, "get_state", MagicMock()).called


@pytest.mark.asyncio
async def test_resilient_storage_falls_back_on_primary_failure() -> None:
    primary = MagicMock()
    primary.get_state = AsyncMock(side_effect=ConnectionError("redis down"))
    primary.set_state = AsyncMock(side_effect=ConnectionError("redis down"))
    primary.set_data = AsyncMock(side_effect=ConnectionError("redis down"))
    primary.get_data = AsyncMock(side_effect=ConnectionError("redis down"))
    primary.close = AsyncMock()

    fallback = MagicMock()
    fallback.set_state = AsyncMock()
    fallback.get_state = AsyncMock(return_value=None)
    fallback.set_data = AsyncMock()
    fallback.get_data = AsyncMock(return_value={})
    fallback.close = AsyncMock()

    storage = ResilientFSMStorage(primary, fallback=fallback)
    state = await storage.get_state(_key())
    # Primary raised, fallback returned None — that's the documented contract.
    assert state is None
    fallback.get_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_resilient_storage_circuit_opens_after_threshold() -> None:
    primary = MagicMock()
    primary.set_state = AsyncMock(side_effect=ConnectionError("down"))
    primary.get_state = AsyncMock(side_effect=ConnectionError("down"))
    primary.close = AsyncMock()

    fallback = MagicMock()
    fallback.set_state = AsyncMock()
    fallback.get_state = AsyncMock(return_value=None)
    fallback.close = AsyncMock()

    breaker = CircuitBreaker(name="test", failure_threshold=2, cool_down_seconds=999)
    storage = ResilientFSMStorage(primary, breaker=breaker, fallback=fallback)

    # First two calls trip the breaker; third bypasses primary entirely.
    await storage.set_state(_key(), "x")
    await storage.set_state(_key(), "x")
    await storage.set_state(_key(), "x")
    # Primary was called only twice (the third call short-circuited).
    assert primary.set_state.await_count == 2
    # Fallback was called all three times.
    assert fallback.set_state.await_count == 3
    assert breaker.state == "open"


@pytest.mark.asyncio
async def test_resilient_storage_update_data_uses_fallback_when_primary_dead() -> None:
    primary = MagicMock()
    primary.get_data = AsyncMock(side_effect=ConnectionError("down"))
    primary.set_data = AsyncMock(side_effect=ConnectionError("down"))
    primary.close = AsyncMock()

    fallback = MagicMock()
    fallback.get_data = AsyncMock(return_value={"existing": 1})
    fallback.set_data = AsyncMock()
    fallback.close = AsyncMock()

    storage = ResilientFSMStorage(primary, fallback=fallback)
    merged = await storage.update_data(_key(), {"new": 2})
    assert merged == {"existing": 1, "new": 2}
    fallback.set_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_resilient_storage_close_closes_both() -> None:
    primary = MagicMock()
    primary.close = AsyncMock()
    fallback = MagicMock()
    fallback.close = AsyncMock()

    storage = ResilientFSMStorage(primary, fallback=fallback)
    await storage.close()
    primary.close.assert_awaited_once()
    fallback.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_resilient_storage_get_data_normalises_none_to_empty() -> None:
    primary = MagicMock()
    primary.get_data = AsyncMock(return_value=None)
    primary.close = AsyncMock()
    fallback = MagicMock()
    fallback.get_data = AsyncMock(return_value=None)
    fallback.close = AsyncMock()

    storage = ResilientFSMStorage(primary, fallback=fallback)
    assert await storage.get_data(_key()) == {}
