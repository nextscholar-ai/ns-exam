"""
Mastery Engine module — Pydantic DTO schemas (Phase 14 §7).

Defines API response shapes for:
  - Topic mastery: per-question breakdown.
  - Chapter mastery: aggregated topic score.
  - Subject mastery: aggregated chapter score.
  - Learning profile: full student mastery summary with weak/strong classification.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TopicMasteryOut(BaseModel):
    """Per-topic mastery response."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    chapter_id: int
    subject_id: int
    mastery_score: float = Field(..., ge=0.0, le=1.0)
    attempt_count: int
    correct_count: int
    last_evaluated_at: datetime | None


class ChapterMasteryOut(BaseModel):
    """Per-chapter mastery response (aggregated from topics)."""

    model_config = ConfigDict(from_attributes=True)

    chapter_id: int
    subject_id: int
    mastery_score: float = Field(..., ge=0.0, le=1.0)
    topic_count: int
    last_updated_at: datetime | None


class SubjectMasteryOut(BaseModel):
    """Per-subject mastery response (aggregated from chapters)."""

    model_config = ConfigDict(from_attributes=True)

    subject_id: int
    mastery_score: float = Field(..., ge=0.0, le=1.0)
    chapter_count: int
    last_updated_at: datetime | None


class LearningProfileOut(BaseModel):
    """
    Full learning profile for a student.

    Includes:
      - Subject-level mastery overview.
      - Lists of weak topics (mastery < WEAK_THRESHOLD = 0.5).
      - Lists of strong topics (mastery >= STRONG_THRESHOLD = 0.8).
    """

    student_id: int
    subject_masteries: list[SubjectMasteryOut]
    chapter_masteries: list[ChapterMasteryOut]
    topic_masteries: list[TopicMasteryOut]
    weak_topic_ids: list[int]
    strong_topic_ids: list[int]


class MasteryHistoryOut(BaseModel):
    """Single mastery update audit record."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    evaluation_id: int
    question_score: float
    mastery_before: float
    mastery_after: float
    alpha_used: float
    evaluated_at: datetime
