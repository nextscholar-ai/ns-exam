"""
Question Bank module - Pydantic DTO schemas.

Defines API contract for creating, updating, searching, importing, versioning,
and querying question bank statistics.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OptionSchema(BaseModel):
    """Option structure for objective questions."""

    label: str = Field(..., json_schema_extra={"example": "A"})
    text: str = Field(..., json_schema_extra={"example": "Paris"})

    image_id: int | None = None


class ObjectiveQuestionCreate(BaseModel):
    """Payload to create an objective question."""

    board_id: int
    class_id: int
    subject_id: int
    primary_chapter_id: int
    primary_unit_id: int | None = None
    primary_topic_id: int | None = None
    question_text: str
    options: list[OptionSchema]
    correct_option: str
    explanation_text: str | None = None
    difficulty: str = "MEDIUM"
    bloom_level: str = "UNDERSTAND"
    marks: float = 1.0


class SubjectiveQuestionCreate(BaseModel):
    """Payload to create a subjective question."""

    board_id: int
    class_id: int
    subject_id: int
    primary_chapter_id: int
    primary_unit_id: int | None = None
    primary_topic_id: int | None = None
    question_text: str
    model_answer_text: str | None = None
    max_marks: float = 5.0
    expected_key_points: list[str] | None = None
    difficulty: str = "MEDIUM"
    bloom_level: str = "ANALYZE"


class FillBlankQuestionCreate(BaseModel):
    """Payload to create a fill-in-the-blank question."""

    board_id: int
    class_id: int
    subject_id: int
    primary_chapter_id: int
    primary_unit_id: int | None = None
    primary_topic_id: int | None = None
    question_text_with_blanks: str
    correct_answers: list[str]
    marks: float = 1.0
    difficulty: str = "EASY"
    bloom_level: str = "REMEMBER"


class QuestionResponse(BaseModel):
    """Unified response payload for any question."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    question_type: str
    question_group_id: int
    board_id: int
    class_id: int
    subject_id: int
    primary_chapter_id: int
    primary_unit_id: int | None = None
    primary_topic_id: int | None = None
    question_text: str
    options: list[dict[str, Any]] | None = None
    correct_option: str | None = None
    explanation_text: str | None = None
    model_answer_text: str | None = None
    max_marks: float | None = None
    expected_key_points: list[str] | None = None
    correct_answers: list[str] | None = None
    marks: float = 1.0
    difficulty: str
    bloom_level: str
    status: str
    version_no: int
    created_at: datetime
    updated_at: datetime


class DuplicateWarningResponse(BaseModel):
    """Warning payload returned when duplicate is detected during import."""

    is_duplicate: bool
    match_type: str | None = None
    score: float = 0.0
    matched_question_public_id: str | None = None
    warning_message: str


class VersionCreateRequest(BaseModel):
    """Payload to create a new version of an existing question."""

    change_reason: str = Field(..., min_length=3)
    updated_data: dict[str, Any]


class VersionResponse(BaseModel):
    """Response payload for a question version entry."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    question_type: str
    version_no: int
    snapshot_json: dict[str, Any]
    change_reason: str | None = None
    is_current: bool
    created_at: datetime


class StatusUpdateRequest(BaseModel):
    """Payload to update question status (DRAFT, ACTIVE, ARCHIVED)."""

    status: str = Field(..., pattern="^(DRAFT|NEEDS_REVIEW|ACTIVE|ARCHIVED)$")


class QuestionStatisticsResponse(BaseModel):
    """Response payload for question statistics."""

    model_config = ConfigDict(from_attributes=True)

    question_type: str
    question_id: int
    usage_count: int
    correct_count: int
    wrong_count: int
    correct_percentage: float
    paper_count: int
    student_count: int
    last_used_at: datetime | None = None


class QuestionSearchFilters(BaseModel):
    """Filters payload for querying question bank."""

    board_id: int | None = None
    class_id: int | None = None
    subject_id: int | None = None
    primary_chapter_id: int | None = None
    difficulty: str | None = None
    bloom_level: str | None = None
    status: str | None = "ACTIVE"
    keyword: str | None = None
    page: int = 1
    page_size: int = 20
