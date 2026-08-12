"""
Analytics Engine module — ORM models (Phase 16 §6).

Tables owned here:
  student_analytics_summaries — cached aggregate performance per student×subject (§6.1).
  class_analytics_summaries   — class-level aggregated performance per class×exam (§6.2).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db.base_model import Base, BaseMixin

_JSON = JSONB().with_variant(JSON(), "sqlite")


class StudentAnalyticsSummary(BaseMixin, Base):
    """
    Cached student performance analytics snapshot (Phase 16 §6.1).

    Aggregates exam attempts, average percentage, mastery trend slope,
    and risk indicators for dashboard display.
    """

    __tablename__ = "student_analytics_summaries"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_sas_student_subject"),
        Index("ix_sas_student_id", "student_id"),
        Index("ix_sas_subject_id", "subject_id"),
        Index("ix_sas_is_at_risk", "is_at_risk"),
    )

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    total_exams_taken: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_exams_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_exams_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_percentage: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0.0
    )
    overall_mastery: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    trend_direction: Mapped[str] = mapped_column(
        String(20), nullable=False, default="STABLE"
    )  # IMPROVING | DECLINING | STABLE
    is_at_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_reasons_json: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ClassAnalyticsSummary(BaseMixin, Base):
    """
    Cached class-level exam performance summary (§6.2).
    """

    __tablename__ = "class_analytics_summaries"
    __table_args__ = (
        UniqueConstraint("class_id", "exam_id", name="uq_cas_class_exam"),
        Index("ix_cas_class_id", "class_id"),
        Index("ix_cas_exam_id", "exam_id"),
    )

    class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("classes.id"), nullable=False
    )
    exam_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exams.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    total_students_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    appeared_students_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_students_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_percentage: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0.0
    )
    class_average_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0.0
    )
    highest_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0.0
    )
    lowest_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0.0
    )
    at_risk_students_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_weak_topic_ids_json: Mapped[list | None] = mapped_column(_JSON, nullable=True)
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
