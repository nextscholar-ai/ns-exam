"""Job status and enqueue request/response schemas (Phase 7 §5.7 / Phase 18 §2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.jobs.registry import JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class BulkImportRequest(BaseModel):
    subject_id: int
    chapter_id: int | None = None
    questions: list[dict[str, Any]] = Field(..., min_length=1)


class BatchReportRequest(BaseModel):
    exam_id: int
    report_type: str = "STUDENT_REPORT_CARD"


class NightlyAnalyticsRequest(BaseModel):
    school_id: int


class JobEnqueueResponse(BaseModel):
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.PENDING
    message: str = "Job enqueued — poll GET /api/v1/jobs/{job_id} for status."
