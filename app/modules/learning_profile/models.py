"""
Mastery Engine module — ORM models (Phase 14 §6).

Tables owned here:
  student_topic_masteries      — rolling EMA mastery per student×topic (§6.1).
  student_chapter_masteries    — aggregated mastery per student×chapter (§6.2).
  student_subject_masteries    — aggregated mastery per student×subject (§6.3).
  mastery_history              — immutable audit trail of every mastery update (§6.4).

Design rules:
  - chapter/topic FK resolution comes ONLY from EvaluationDetail.chapter_id/topic_id (never typed manually).
  - mastery_score is always 0.0–1.0 (enforced in service layer).
  - mastery_history is append-only (soft-delete allowed but data never overwritten).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base_model import Base, BaseMixin


class StudentTopicMastery(BaseMixin, Base):
    """
    Rolling mastery score for one student × one topic (§6.1).

    Updated on every EvaluationCompleted event using Exponential Moving Average.
    Consumed by Phase 15 (Recommendation Engine) to identify weak topics.
    """

    __tablename__ = "student_topic_masteries"
    __table_args__ = (
        UniqueConstraint("student_id", "topic_id", name="uq_stm_student_topic"),
        Index("ix_stm_student_id", "student_id"),
        Index("ix_stm_topic_id", "topic_id"),
        Index("ix_stm_mastery_score", "mastery_score"),
    )

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chapters.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    mastery_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )  # 0.0000 – 1.0000
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    correct_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StudentChapterMastery(BaseMixin, Base):
    """
    Aggregated chapter mastery — average of all topic masteries in the chapter (§6.2).
    Recomputed on every EvaluationCompleted event that touches the chapter.
    """

    __tablename__ = "student_chapter_masteries"
    __table_args__ = (
        UniqueConstraint("student_id", "chapter_id", name="uq_scm_student_chapter"),
        Index("ix_scm_student_id", "student_id"),
        Index("ix_scm_chapter_id", "chapter_id"),
    )

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chapters.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    mastery_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    topic_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StudentSubjectMastery(BaseMixin, Base):
    """
    Aggregated subject mastery — average of all chapter masteries (§6.3).
    Recomputed on every EvaluationCompleted event that touches the subject.
    """

    __tablename__ = "student_subject_masteries"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_ssm_student_subject"),
        Index("ix_ssm_student_id", "student_id"),
        Index("ix_ssm_subject_id", "subject_id"),
    )

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    mastery_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    chapter_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MasteryHistory(BaseMixin, Base):
    """
    Immutable audit trail — one row per topic mastery update event (§6.4).
    Used by Phase 16 (Analytics) for trend graphs and Progress Reports.
    """

    __tablename__ = "mastery_history"
    __table_args__ = (
        Index("ix_mh_student_id", "student_id"),
        Index("ix_mh_topic_id", "topic_id"),
        Index("ix_mh_evaluation_id", "evaluation_id"),
    )

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("topics.id"), nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chapters.id"), nullable=False
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False
    )
    evaluation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evaluations.id"), nullable=False
    )
    # Raw question score for this topic in this evaluation (0.0–1.0)
    question_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    # EMA mastery score BEFORE this update
    mastery_before: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    # EMA mastery score AFTER this update
    mastery_after: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    # EMA smoothing factor used (α)
    alpha_used: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
