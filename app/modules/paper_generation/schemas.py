"""
Paper Generation module — Pydantic DTO schemas (Phase 11).

DTOs cover paper generation requests, teacher review actions,
validation results, and AI explainability responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Paper Generation Request
# ---------------------------------------------------------------------------

class PaperGenerateRequest(BaseModel):
    """
    Triggers paper generation for an exam configuration.

    student_ids: empty list → generate one shared non-personalized paper.
                 Non-empty → one paper per listed student_id (personalized).
    """

    exam_configuration_id: int
    student_ids: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Teacher Review Actions
# ---------------------------------------------------------------------------

class QuestionReplaceRequest(BaseModel):
    """Replace one question in a paper; creates a new PaperVersion."""

    replacement_question_type: str = Field(
        ...,
        pattern="^(OBJECTIVE|SUBJECTIVE|FILL_BLANK)$",
    )
    replacement_question_id: int
    change_reason: str = Field(..., min_length=5)


class PaperApproveRequest(BaseModel):
    """Approve a paper; changes status UNDER_REVIEW → APPROVED."""

    notes: str | None = None


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class PaperQuestionResponse(BaseModel):
    """Single question slot inside a paper section."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    question_type: str
    question_id: int
    sequence_no: int
    marks: float
    selection_reason_json: dict[str, Any] | None


class PaperSectionResponse(BaseModel):
    """Section header with its ordered question list."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    section_label: str
    question_type: str
    section_marks: float
    questions: list[PaperQuestionResponse] = Field(default_factory=list)


class PaperResponse(BaseModel):
    """Full paper response (without questions — for list endpoints)."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    exam_configuration_id: int
    blueprint_id: int
    student_id: int | None
    status: str
    total_marks: float
    version_no: int
    generated_at: datetime | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaperDetailResponse(PaperResponse):
    """Full paper response with nested sections and questions."""

    sections: list[PaperSectionResponse] = Field(default_factory=list)


class PaperValidationResponse(BaseModel):
    """One validation rule result."""

    model_config = ConfigDict(from_attributes=True)

    rule_code: str
    passed: bool
    detail: str | None


class PaperVersionResponse(BaseModel):
    """One version entry in a paper's version history."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    paper_id: int
    version_no: int
    snapshot_json: dict[str, Any]
    change_reason: str | None
    is_current: bool
    created_at: datetime


class AILogResponse(BaseModel):
    """Explainability row for one candidate question."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    question_type: str
    question_id: int
    blueprint_match_score: float
    difficulty_match_score: float
    weak_topic_match_score: float
    usage_balance_score: float
    bloom_match_score: float
    final_rank_score: float
    selected: bool


class GenerationJobResponse(BaseModel):
    """Status response for an async paper generation job."""

    job_id: str
    status: str
    total: int
    completed: int
    paper_public_ids: list[str] = Field(default_factory=list)
