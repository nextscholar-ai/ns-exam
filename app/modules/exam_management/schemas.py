"""
Exam Management module — Pydantic DTO schemas (Phase 12).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExamCreate(BaseModel):
    """Payload to create a new Exam in DRAFT state."""

    board_id: int
    school_id: int
    class_id: int
    subject_id: int
    title: str = Field(..., min_length=3, max_length=255)
    exam_type: str = Field(default="REGULAR", pattern="^(REGULAR|MOCK)$")


class ExamConfigure(BaseModel):
    """Payload to link an exam_configuration to an exam."""

    exam_configuration_id: int


class ExamSchedule(BaseModel):
    """Payload to schedule an exam."""

    scheduled_start_at: datetime
    scheduled_end_at: datetime


class ExamResponse(BaseModel):
    """Unified response payload for Exam."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    exam_configuration_id: int | None = None
    board_id: int
    school_id: int
    class_id: int
    subject_id: int
    title: str
    status: str
    exam_type: str
    scheduled_start_at: datetime | None = None
    scheduled_end_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    published_at: datetime | None = None
    join_code: str | None = None
    created_at: datetime
    updated_at: datetime


class GuestJoinRequest(BaseModel):
    """Payload for guest student joining an exam via join code."""

    join_code: str = Field(..., min_length=4, max_length=20)
    guest_name: str = Field(..., min_length=2, max_length=100)


class GuestJoinResponse(BaseModel):
    """Response payload for guest joining an exam."""

    exam_public_id: UUID
    student_id: int
    paper_public_id: UUID
    join_code: str


class AttemptStartRequest(BaseModel):
    """Payload to start an exam attempt."""

    student_id: int


class AttemptSubmitRequest(BaseModel):
    """Payload to submit an ongoing attempt."""

    attempt_public_id: UUID
    answers_summary_json: dict[str, Any] | None = None


class StudentAttemptResponse(BaseModel):
    """Response payload for a student attempt."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    exam_id: int
    student_id: int
    paper_id: int
    attempt_number: int
    status: str
    started_at: datetime
    submitted_at: datetime | None = None
    is_latest: bool
    created_at: datetime


class ExamStatusHistoryResponse(BaseModel):
    """Audit response for exam state machine history."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    from_status: str
    to_status: str
    changed_by: int | None = None
    changed_at: datetime
