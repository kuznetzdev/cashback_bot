"""Scheduler managing notification jobs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ScheduledJob:
    chat_id: int
    job_type: str
    schedule: str


class SchedulerService:
    """Keeps track of notification schedules."""

    def __init__(self) -> None:
        self._jobs: Dict[int, List[ScheduledJob]] = {}

    def schedule(self, chat_id: int, job_type: str, schedule: str) -> ScheduledJob:
        job = ScheduledJob(chat_id=chat_id, job_type=job_type, schedule=schedule)
        self._jobs.setdefault(chat_id, []).append(job)
        return job

    def cancel(self, chat_id: int, job_type: str) -> None:
        jobs = self._jobs.get(chat_id, [])
        self._jobs[chat_id] = [job for job in jobs if job.job_type != job_type]

    def list_jobs(self, chat_id: int) -> List[ScheduledJob]:
        return list(self._jobs.get(chat_id, []))


__all__ = ["SchedulerService", "ScheduledJob"]
