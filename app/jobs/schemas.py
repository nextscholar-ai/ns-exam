"""Job status response schemas (Phase 7 §5.7)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.jobs.registry import JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
