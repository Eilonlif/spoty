"""A tiny in-memory job registry for tracking conversion progress.

Conversions can take a while (especially playlists), so the web layer starts
a background thread per job and the browser polls for progress. State lives in
memory, which is fine for a single-process local app.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    """Tracks the lifecycle of one conversion request."""

    id: str
    url: str
    status: JobStatus = JobStatus.PENDING
    message: str = "Queued"
    total: int = 0           # number of tracks
    completed: int = 0       # tracks finished
    result_path: Path | None = None
    result_name: str | None = None  # friendly download filename
    error: str | None = None

    @property
    def progress(self) -> int:
        """Completion percentage (0-100)."""
        if self.total <= 0:
            return 0
        return int(self.completed / self.total * 100)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "message": self.message,
            "total": self.total,
            "completed": self.completed,
            "progress": self.progress,
            "result_name": self.result_name,
            "error": self.error,
        }


class JobRegistry:
    """Thread-safe store of Job objects."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, url: str) -> Job:
        job = Job(id=uuid.uuid4().hex, url=url)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
