"""
Analytics Engine module — Pydantic DTO schemas (Phase 16 §7).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StudentAnalyticsDashboard(BaseModel):
    """Full student performance analytics dashboard payload."""

    model_config = ConfigDict(from_attributes=True)

    student_id: int
    subject_id: int
    total_exams_taken: int
    passed_exams_count: int
    failed_exams_count: int
    average_percentage: float
    overall_mastery: float
    trend_direction: str  # IMPROVING | DECLINING | STABLE
    is_at_risk: bool
    risk_reasons: list[str] = []
    weak_topic_ids: list[int] = []
    strong_topic_ids: list[int] = []
    recent_attempts_summary: list[dict[str, Any]] = []
    last_computed_at: datetime


class ClassAnalyticsDashboard(BaseModel):
    """Class-level exam performance dashboard payload."""

    model_config = ConfigDict(from_attributes=True)

    class_id: int
    exam_id: int
    subject_id: int
    total_students_count: int
    appeared_students_count: int
    passed_students_count: int
    pass_percentage: float
    class_average_score: float
    highest_score: float
    lowest_score: float
    at_risk_students_count: int
    top_weak_topic_ids: list[int] = []
    last_computed_at: datetime
