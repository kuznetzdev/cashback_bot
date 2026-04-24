from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.telegram.router import _with_typing


@pytest.mark.asyncio
async def test_with_typing_sends_initial_chat_action() -> None:
    bot = AsyncMock()
    bot.send_chat_action = AsyncMock()

    async def work() -> str:
        # Yield once so the refresher task gets a chance to fire the initial action.
        await asyncio.sleep(0)
        return "done"

    result = await _with_typing(bot=bot, chat_id=42, coro=work())
    assert result == "done"
    # At least one chat_action call with the "typing" action.
    assert bot.send_chat_action.await_count >= 1
    first_args = bot.send_chat_action.await_args_list[0].args
    assert first_args == (42, "typing")


@pytest.mark.asyncio
async def test_with_typing_cancels_refresher_after_coroutine_completes() -> None:
    bot = AsyncMock()
    bot.send_chat_action = AsyncMock()
    pre_tasks = {task for task in asyncio.all_tasks() if task is not asyncio.current_task()}

    async def work() -> None:
        await asyncio.sleep(0)

    await _with_typing(bot=bot, chat_id=1, coro=work())

    await asyncio.sleep(0)
    post_tasks = {task for task in asyncio.all_tasks() if task is not asyncio.current_task()}
    # No new refresher tasks leaked past the helper's lifetime.
    new_tasks = post_tasks - pre_tasks
    remaining = [task for task in new_tasks if not task.done()]
    assert remaining == []


@pytest.mark.asyncio
async def test_with_typing_propagates_exception_from_coroutine() -> None:
    bot = AsyncMock()
    bot.send_chat_action = AsyncMock()

    async def failing() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await _with_typing(bot=bot, chat_id=1, coro=failing())
    # Even on exception the refresher cleanup must not swallow the error.


@pytest.mark.asyncio
async def test_with_typing_survives_send_chat_action_failure() -> None:
    bot = AsyncMock()
    bot.send_chat_action = AsyncMock(side_effect=RuntimeError("network"))

    async def work() -> str:
        await asyncio.sleep(0)
        return "ok"

    # The refresher must not bubble the send_chat_action failure up.
    result = await _with_typing(bot=bot, chat_id=1, coro=work())
    assert result == "ok"
