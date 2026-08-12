"""
Reporting Engine module — Pydantic DTO schemas (Phase 16 §7.5).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportGenerateRequest(BaseModel):
    """Payload to trigger report snapshot generation."""

    report_type: str  # STUDENT_PROGRESS | EXAM_ANALYSIS | CLASS_PERFORMANCE
    student_id: int | None = None
    class_id: int | None = None
    exam_id: int | None = None
    title: str | None = None


class ReportSnapshotResponse(BaseModel):
    """Response payload for a report snapshot."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    report_type: str
    status: str
    student_id: int | None
    class_id: int | None
    exam_id: int | None
    title: str
    summary_text: str | None
    report_data_json: dict[str, Any]
    generated_by: str | None
    published_at: datetime | None
    created_at: datetime
