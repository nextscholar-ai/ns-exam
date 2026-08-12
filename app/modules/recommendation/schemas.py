"""
Recommendation Engine module — Pydantic DTO schemas (Phase 15 §7).

Defines API payloads and response shapes for:
  - Generating practice recommendations.
  - Recommendation item details.
  - Accepting / dismissing recommendations.
  - Submitting feedback.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecommendationGenerateRequest(BaseModel):
    """Payload to trigger recommendation generation for a student."""

    subject_id: int
    recommendation_type: str = "PRACTICE_SET"  # PRACTICE_SET | PERSONALIZED_MOCK | REVISION_FLASHCARDS
    item_count: int = Field(default=5, ge=1, le=20)
    target_difficulty: str | None = None  # EASY | MEDIUM | HARD | ADAPTIVE


class RecommendationFeedbackCreate(BaseModel):
    """Payload to submit student/teacher feedback."""

    rating: str  # HELPFUL | TOO_EASY | TOO_HARD | NOT_RELEVANT
    comments: str | None = None


class RecommendationItemResponse(BaseModel):
    """Individual item in a recommendation response."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    chapter_id: int
    question_type: str
    question_id: int | None
    sequence_no: int
    reason_json: dict[str, Any] | None


class RecommendationResponse(BaseModel):
    """Full recommendation response."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    student_id: int
    subject_id: int
    recommendation_type: str
    status: str
    target_topic_ids_json: list[int]
    recommended_difficulty: str
    priority_score: float
    item_count: int
    generated_paper_id: int | None
    expires_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    items: list[RecommendationItemResponse] = []
