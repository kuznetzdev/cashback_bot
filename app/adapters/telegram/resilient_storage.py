"""Resilient FSM storage wrapper.

Wraps an aiogram :class:`BaseStorage` (typically RedisStorage) and falls
back to an in-memory storage when the primary fails. The fallback is
guarded by a circuit breaker so a partial outage doesn't translate into
an N-times-per-update retry storm against an unreachable Redis.

State stored in the in-memory fallback while Redis is down is **lost**
when Redis recovers. That's the same loss profile as if the user's bot
restarted mid-wizard with `FSM_STORAGE=memory` — accepted as the price
of staying responsive during a Redis incident, vs the alternative of
the bot returning errors on every step.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.adapters.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)


class ResilientFSMStorage(BaseStorage):
    """Primary + fallback aiogram storage with breaker-driven failover."""

    def __init__(
        self,
        primary: BaseStorage,
        *,
        breaker: CircuitBreaker | None = None,
        fallback: BaseStorage | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or MemoryStorage()
        # Trip after 5 consecutive primary errors, retry primary after 60 s.
        # Tuned so a Redis hiccup (network blip, brief pod restart) doesn't
        # immediately abandon Redis but a true outage moves traffic to
        # memory without burning every request on the failed primary.
        self._breaker = breaker or CircuitBreaker(
            name="fsm_storage_primary",
            failure_threshold=5,
            cool_down_seconds=60.0,
        )

    @property
    def state(self) -> str:
        return self._breaker.state

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        await self._call("set_state", key, state)

    async def get_state(self, key: StorageKey) -> str | None:
        return await self._call("get_state", key)

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await self._call("set_data", key, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        result = await self._call("get_data", key)
        return result or {}

    async def update_data(self, key: StorageKey, data: dict[str, Any]) -> dict[str, Any]:
        # update_data has read-modify-write semantics; if either step fails
        # we still need the merged dict, so do the merge in-Python and use
        # set_data for the write.
        current = await self.get_data(key)
        current.update(data)
        await self.set_data(key, current)
        return current

    async def close(self) -> None:
        try:
            await self._primary.close()
        except Exception as error:  # pragma: no cover - best-effort
            logger.debug("Primary FSM close raised: %s", error)
        try:
            await self._fallback.close()
        except Exception as error:  # pragma: no cover - best-effort
            logger.debug("Fallback FSM close raised: %s", error)

    async def _call(self, method: str, *args: Any) -> Any:
        primary_method = getattr(self._primary, method)
        fallback_method = getattr(self._fallback, method)
        try:
            return await self._breaker.call(primary_method, *args)
        except CircuitOpenError:
            logger.debug(
                "FSM primary breaker open — using fallback for %s",
                method,
            )
            return await fallback_method(*args)
        except Exception as error:
            # Log once per call — repeated logging during a sustained outage
            # is suppressed by the breaker after the threshold trips.
            logger.warning(
                "FSM primary %s failed (%s) — falling back to memory",
                method,
                error.__class__.__name__,
            )
            return await fallback_method(*args)
