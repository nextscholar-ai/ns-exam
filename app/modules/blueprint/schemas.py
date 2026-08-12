"""
Blueprint module — Pydantic DTO schemas (Phase 11).

All DTOs use ConfigDict(from_attributes=True) so ORM instances can be
serialized directly via model_validate() without extra mapping code.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

class SectionDifficultyDistribution(BaseModel):
    """Validates difficulty percentages sum to ~100."""

    EASY: int = Field(default=30, ge=0, le=100)
    MEDIUM: int = Field(default=50, ge=0, le=100)
    HARD: int = Field(default=20, ge=0, le=100)

    @model_validator(mode="after")
    def _sum_100(self) -> "SectionDifficultyDistribution":
        total = self.EASY + self.MEDIUM + self.HARD
        if total != 100:
            raise ValueError(
                f"difficulty_distribution must sum to 100, got {total}"
            )
        return self


class BlueprintSectionCreate(BaseModel):
    """Payload to define one section inside a blueprint."""

    section_label: str = Field(..., min_length=1, max_length=10)
    question_type: str = Field(
        ...,
        pattern="^(OBJECTIVE|SUBJECTIVE|FILL_BLANK)$",
    )
    section_marks: float = Field(..., gt=0)
    question_count: int = Field(..., ge=1)
    difficulty_distribution: SectionDifficultyDistribution = Field(
        default_factory=SectionDifficultyDistribution
    )
    bloom_distribution: dict[str, int] | None = None
    chapter_scope: list[int] | None = None


class BlueprintCreate(BaseModel):
    """Payload to create a new blueprint."""

    board_id: int
    class_id: int
    subject_id: int
    name: str = Field(..., min_length=3, max_length=255)
    total_marks: float = Field(..., gt=0)
    duration_minutes: int = Field(..., ge=5)
    syllabus_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    sections: list[BlueprintSectionCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _section_marks_match_total(self) -> "BlueprintCreate":
        section_total = sum(s.section_marks for s in self.sections)
        if abs(section_total - self.total_marks) > 0.01:
            raise ValueError(
                f"Sum of section marks ({section_total}) must equal "
                f"total_marks ({self.total_marks})"
            )
        return self


class BlueprintResponse(BaseModel):
    """Response payload for a blueprint."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    board_id: int
    class_id: int
    subject_id: int
    name: str
    total_marks: float
    duration_minutes: int
    syllabus_coverage_pct: float | None
    status: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ExamConfiguration
# ---------------------------------------------------------------------------

class ExamConfigCreate(BaseModel):
    """Payload to create an exam configuration."""

    blueprint_id: int
    exam_name: str = Field(..., min_length=3, max_length=255)
    academic_session_id: int
    exam_type: str = Field(default="REGULAR", pattern="^(REGULAR|MOCK)$")
    personalized: bool = False
    current_chapters: list[int] | None = None
    current_topics: list[int] | None = None
    exam_date: datetime | None = None
    publish_date: datetime | None = None


class ExamConfigResponse(BaseModel):
    """Response payload for an exam configuration."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    blueprint_id: int
    exam_name: str
    academic_session_id: int
    exam_type: str
    personalized: bool
    status: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Status update (reusable pattern across both Blueprint & ExamConfig)
# ---------------------------------------------------------------------------

class StatusUpdateRequest(BaseModel):
    """Generic status update payload."""

    status: str = Field(
        ...,
        pattern="^(DRAFT|ACTIVE|ARCHIVED)$",
    )


class BlueprintSectionResponse(BaseModel):
    """Response payload for a blueprint section."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    blueprint_id: int
    section_label: str
    question_type: str
    section_marks: float
    question_count: int
    difficulty_distribution_json: dict[str, Any]
    bloom_distribution_json: dict[str, Any] | None
    chapter_scope_json: list[int] | None
