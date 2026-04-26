from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.adapters.circuit_breaker import CircuitBreaker, CircuitOpenError


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_breaker_starts_closed() -> None:
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_seconds=10.0)
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_breaker_passes_through_successful_calls() -> None:
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_seconds=10.0)
    func = AsyncMock(return_value="ok")
    result = await cb.call(func, 42, key="value")
    assert result == "ok"
    func.assert_awaited_once_with(42, key="value")
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_breaker_trips_after_threshold() -> None:
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_seconds=10.0)
    failing = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await cb.call(failing)
    assert cb.state == "closed"
    with pytest.raises(RuntimeError):
        await cb.call(failing)
    assert cb.state == "open"
    assert cb.stats.trips == 1
    assert cb.stats.consecutive_failures == 2


@pytest.mark.asyncio
async def test_breaker_short_circuits_when_open() -> None:
    cb = CircuitBreaker(name="test", failure_threshold=1, cool_down_seconds=10.0)
    failing = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await cb.call(failing)
    assert cb.state == "open"

    # Second call doesn't even hit the inner function.
    inner = AsyncMock(return_value="should not run")
    with pytest.raises(CircuitOpenError):
        await cb.call(inner)
    inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_breaker_half_open_after_cool_down_then_closes_on_success() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(name="test", failure_threshold=1, cool_down_seconds=10.0, clock=clock)
    failing = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await cb.call(failing)
    assert cb.state == "open"

    # Advance past the cool-down — next call probes.
    clock.tick(11.0)
    success = AsyncMock(return_value="ok")
    result = await cb.call(success)
    assert result == "ok"
    assert cb.state == "closed"
    assert cb.stats.consecutive_failures == 0


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens_immediately() -> None:
    clock = _FakeClock()
    cb = CircuitBreaker(name="test", failure_threshold=1, cool_down_seconds=10.0, clock=clock)

    failing = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await cb.call(failing)
    assert cb.state == "open"
    initial_trips = cb.stats.trips

    clock.tick(11.0)
    # Probe fails — single failure in half-open should re-trip without
    # waiting for the threshold to be reached again.
    with pytest.raises(RuntimeError):
        await cb.call(failing)
    assert cb.state == "open"
    assert cb.stats.trips == initial_trips + 1


@pytest.mark.asyncio
async def test_breaker_treats_predicate_match_as_failure() -> None:
    cb = CircuitBreaker(name="test", failure_threshold=2, cool_down_seconds=10.0)

    async def returns_none() -> None:
        return None

    await cb.call(returns_none, is_failure=lambda result: result is None)
    await cb.call(returns_none, is_failure=lambda result: result is None)
    assert cb.state == "open"


@pytest.mark.asyncio
async def test_breaker_rejects_invalid_construction_args() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker(name="x", failure_threshold=0, cool_down_seconds=10.0)
    with pytest.raises(ValueError):
        CircuitBreaker(name="x", failure_threshold=1, cool_down_seconds=0)
