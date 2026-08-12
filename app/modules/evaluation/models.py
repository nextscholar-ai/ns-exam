"""
Evaluation Engine module — ORM models (Phase 13 §6).

Tables owned here:
  evaluations              — aggregate root (one per student_attempts row).
  evaluation_details      — question-wise marks with auto-mapped chapter_id/topic_id (§6.2).
  omr_uploads              — scanned sheet upload metadata (§6.3).
  omr_results              — detected bubbles & confidence audit (§6.3).
  subjective_evaluations   — subjective answer PDF submission metadata (§6.4).
  evaluation_versions      — immutable re-evaluation audit snapshot history (§6.5).
  re_evaluation_requests   — admin/teacher re-evaluation request tracking (§6.6).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BIGINT,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db.base_model import Base, BaseMixin

_JSON = JSONB().with_variant(JSON(), "sqlite")


class Evaluation(BaseMixin, Base):
    """
    Evaluation Aggregate Root (Phase 13 §6.1).

    One row per student_attempts entry (UNIQUE FK attempt_id).
    """

    __tablename__ = "evaluations"
    __table_args__ = (
        Index("uq_evaluations_attempt_id", "attempt_id", unique=True),
        Index("ix_evaluations_status", "status"),
    )

    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_attempts.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING"
    )
    objective_marks: Mapped[float | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    subjective_marks: Mapped[float | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    total_marks: Mapped[float | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    percentage: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    result_status: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # PASS | FAIL
    locked_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_version_no: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1
    )

    details: Mapped[list["EvaluationDetail"]] = relationship(
        back_populates="evaluation",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    versions: Mapped[list["EvaluationVersion"]] = relationship(
        back_populates="evaluation",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class EvaluationDetail(BaseMixin, Base):
    """
    Question-wise marks obtained (§6.2).
    Critical row for Phase 14 Mastery Engine: chapter_id and topic_id are
    AUTO-RESOLVED from question metadata, never typed by teacher.
    """

    __tablename__ = "evaluation_details"
    __table_args__ = (
        Index("ix_evaluation_details_eval_id", "evaluation_id"),
        Index("ix_evaluation_details_chapter_topic", "chapter_id", "topic_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evaluations.id"), nullable=False
    )
    paper_question_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("paper_questions.id"), nullable=True
    )
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id"), nullable=True
    )
    topic_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("topics.id"), nullable=True
    )
    marks_obtained: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_marks: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evaluated_by: Mapped[str] = mapped_column(
        String(10), nullable=False, default="OMR"
    )  # OMR | TEACHER
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    evaluation: Mapped["Evaluation"] = relationship(
        back_populates="details",
        lazy="raise",
    )


class OMRUpload(BaseMixin, Base):
    """Scanned OMR sheet upload metadata (§6.3)."""

    __tablename__ = "omr_uploads"
    __table_args__ = (
        Index("ix_omr_uploads_attempt_id", "attempt_id"),
    )

    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_attempts.id"), nullable=False
    )
    file_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("files.id"), nullable=True
    )
    upload_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="WEB_UPLOAD"
    )  # WEB_UPLOAD | SCANNER
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING | PROCESSING | DETECTED | FAILED | NEEDS_MANUAL_REVIEW

    result: Mapped["OMRResult | None"] = relationship(
        back_populates="upload",
        uselist=False,
        lazy="raise",
        cascade="all, delete-orphan",
    )


class OMRResult(BaseMixin, Base):
    """Detected bubbles and confidence audit data (§6.3)."""

    __tablename__ = "omr_results"
    __table_args__ = (
        Index("ix_omr_results_upload_id", "omr_upload_id"),
    )

    omr_upload_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("omr_uploads.id"), nullable=False, unique=True
    )
    detected_grid_json: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    detected_answers_json: Mapped[dict] = mapped_column(_JSON, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    low_confidence_questions_json: Mapped[list | None] = mapped_column(_JSON, nullable=True)

    upload: Mapped["OMRUpload"] = relationship(
        back_populates="result",
        lazy="raise",
    )


class SubjectiveEvaluation(BaseMixin, Base):
    """Subjective answer PDF evaluation submission metadata (§6.4)."""

    __tablename__ = "subjective_evaluations"
    __table_args__ = (
        Index("ix_subjective_evaluations_eval_id", "evaluation_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evaluations.id"), nullable=False
    )
    answer_file_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("files.id"), nullable=True
    )
    evaluated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EvaluationVersion(BaseMixin, Base):
    """Immutable audit trail snapshot for re-evaluation (§6.5)."""

    __tablename__ = "evaluation_versions"
    __table_args__ = (
        Index("ix_evaluation_versions_eval_id", "evaluation_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evaluations.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(_JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    evaluation: Mapped["Evaluation"] = relationship(
        back_populates="versions",
        lazy="raise",
    )


class ReEvaluationRequest(BaseMixin, Base):
    """Re-evaluation request tracking (§6.6)."""

    __tablename__ = "re_evaluation_requests"
    __table_args__ = (
        Index("ix_re_evaluation_requests_eval_id", "evaluation_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evaluations.id"), nullable=False
    )
    requested_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING | APPROVED | REJECTED | COMPLETED
    approved_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
