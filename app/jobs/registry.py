"""
Async/long-running-operation job registry (Phase 7 §5.7 / Phase 18 §2).

Endpoints that trigger background work (bulk paper generation, OMR batch
processing) return `202 Accepted` with a `job_id` immediately, then the
client polls `GET /api/v1/jobs/{job_id}`. Phase 18 adds real task execution;
this module owns the API-visible contract and in-memory backing store.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Job:
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # Phase 18: arbitrary job metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job_type: str, meta: dict[str, Any] | None = None) -> Job:
        job = Job(job_id=str(uuid.uuid4()), job_type=job_type, meta=meta or {})
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_recent(self, limit: int = 20) -> list[Job]:
        """Return the most recently created jobs (newest first)."""
        with self._lock:
            sorted_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
        return sorted_jobs[:limit]

    def list_by_type(self, job_type: str, limit: int = 20) -> list[Job]:
        """Return recent jobs of a specific type."""
        with self._lock:
            filtered = [j for j in self._jobs.values() if j.job_type == job_type]
            sorted_jobs = sorted(filtered, key=lambda j: j.created_at, reverse=True)
        return sorted_jobs[:limit]

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, status=JobStatus.RUNNING)

    def mark_completed(self, job_id: str, result: dict[str, Any]) -> None:
        self._update(job_id, status=JobStatus.COMPLETED, result=result)

    def mark_failed(self, job_id: str, error: str) -> None:
        self._update(job_id, status=JobStatus.FAILED, error=error)

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = datetime.now(timezone.utc)


job_registry = JobRegistry()
