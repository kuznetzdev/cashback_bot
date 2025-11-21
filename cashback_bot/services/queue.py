from __future__ import annotations

"""In-memory safe queue for OCR tasks."""
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class QueueTask:
    user_id: int
    bank_name: str
    image_bytes: bytes


class WorkflowQueue:
    def __init__(self) -> None:
        self._queues: Dict[int, asyncio.Queue[QueueTask]] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def get_queue(self, user_id: int) -> asyncio.Queue[QueueTask]:
        if user_id not in self._queues:
            self._queues[user_id] = asyncio.Queue()
        return self._queues[user_id]

    def get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def enqueue(self, task: QueueTask) -> None:
        await self.get_queue(task.user_id).put(task)

    async def next_task(self, user_id: int) -> Optional[QueueTask]:
        queue = self.get_queue(user_id)
        if queue.empty():
            return None
        return await queue.get()

    async def has_pending(self, user_id: int) -> bool:
        queue = self.get_queue(user_id)
        return not queue.empty()
