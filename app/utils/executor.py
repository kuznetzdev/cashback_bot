from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Callable


async def run_blocking(
    func: Callable[..., Any],
    *args: Any,
    timeout: int | None = None,
) -> Any:
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(None, partial(func, *args))
    if timeout is None:
        return await task
    return await asyncio.wait_for(task, timeout=timeout)
