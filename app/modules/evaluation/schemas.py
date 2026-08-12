"""
Evaluation Engine module — Pydantic DTO schemas (Phase 13).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OMRUploadRequest(BaseModel):
    """Payload to trigger OMR scanning and bubble detection."""

    attempt_id: int
    raw_bubble_matrix: dict[str, dict[str, float]] | None = None
    upload_source: str = Field(default="WEB_UPLOAD", pattern="^(WEB_UPLOAD|SCANNER)$")


class OMRManualReviewRequest(BaseModel):
    """Payload for resolving flagged low-confidence OMR questions."""

    corrected_answers: dict[str, str]  # {"1": "B", "2": "A"}


class SubjectiveMarksEntry(BaseModel):
    """Payload for teacher entering question-wise subjective marks."""

    question_id: int
    marks_obtained: float = Field(..., ge=0)
    comments: str | None = None


class EvaluationCompleteRequest(BaseModel):
    """Payload to compute totals and transition to COMPLETED."""

    pass_threshold_pct: float = Field(default=40.0, ge=0, le=100)


class ReEvaluationRequestCreate(BaseModel):
    """Payload to request re-evaluation of a locked evaluation."""

    reason: str = Field(..., min_length=5, max_length=500)


class EvaluationDetailResponse(BaseModel):
    """Response payload for a single question evaluation detail."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    question_type: str
    question_id: int
    chapter_id: int | None = None
    topic_id: int | None = None
    marks_obtained: float
    max_marks: float
    is_correct: bool | None = None
    evaluated_by: str
    evaluated_at: datetime


class OMRResultResponse(BaseModel):
    """Response payload for OMR detection results."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    omr_upload_id: int
    detected_answers_json: dict[str, Any]
    confidence_score: float
    low_confidence_questions_json: list[dict[str, Any]] | None = None


class EvaluationResponse(BaseModel):
    """Response payload for full Evaluation."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    attempt_id: int
    status: str
    objective_marks: float | None = None
    subjective_marks: float | None = None
    total_marks: float | None = None
    percentage: float | None = None
    result_status: str | None = None
    locked_at: datetime | None = None
    current_version_no: int
    created_at: datetime
    updated_at: datetime


class EvaluationVersionResponse(BaseModel):
    """Response payload for re-evaluation audit snapshot version."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    version_no: int
    snapshot_json: dict[str, Any]
    reason: str | None = None
    created_at: datetime
