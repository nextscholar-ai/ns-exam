"""
Exam Management module — ORM models (Phase 12 §6).

Tables owned here:
  exams                      — aggregate root tracking exam lifecycle state.
  exam_status_history        — append-only log of state machine transitions (§6.2).
  exam_student_assignments   — link table assigning papers to students (§6.3).
  student_attempts           — student attempt execution rows (Regular vs Mock, §6.4).
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
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base_model import Base, BaseMixin


class Exam(BaseMixin, Base):
    """
    Aggregate Root for Exam Management (Phase 12 §6.1).

    Status is strictly mutated via state_machine transition validation.
    """

    __tablename__ = "exams"
    __table_args__ = (
        Index("ix_exams_board_school_class_subject", "board_id", "school_id", "class_id", "subject_id"),
        Index("ix_exams_status", "status"),
        Index("ix_exams_join_code", "join_code"),
    )

    exam_configuration_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("exam_configurations.id"),
        nullable=True,
    )
    board_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("boards.id"),
        nullable=False,
    )
    school_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("schools.id"),
        nullable=False,
    )
    class_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("classes.id"),
        nullable=False,
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subjects.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT"
    )
    exam_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="REGULAR"
    )  # REGULAR | MOCK
    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    join_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True
    )

    history: Mapped[list["ExamStatusHistory"]] = relationship(
        back_populates="exam",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[list["ExamStudentAssignment"]] = relationship(
        back_populates="exam",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    attempts: Mapped[list["StudentAttempt"]] = relationship(
        back_populates="exam",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class ExamStatusHistory(Base, BaseMixin):
    """
    Append-only audit trail for exam lifecycle transitions (§6.2).
    """

    __tablename__ = "exam_status_history"
    __table_args__ = (
        Index("ix_exam_status_history_exam_id", "exam_id"),
    )

    exam_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exams.id"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    exam: Mapped["Exam"] = relationship(
        back_populates="history",
        lazy="raise",
    )


class ExamStudentAssignment(BaseMixin, Base):
    """
    Student to Paper assignment within an Exam (§6.3).
    """

    __tablename__ = "exam_student_assignments"
    __table_args__ = (
        Index("uq_exam_student_assignments", "exam_id", "student_id", unique=True),
    )

    exam_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exams.id"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ASSIGNED"
    )  # ASSIGNED | STARTED | SUBMITTED | EXPIRED

    exam: Mapped["Exam"] = relationship(
        back_populates="assignments",
        lazy="raise",
    )


class StudentAttempt(BaseMixin, Base):
    """
    Student exam execution attempts (§6.4).
    Regular exams: attempt_number=1, exactly one attempt.
    Mock exams: attempt_number=1..N, is_latest=True for the active attempt.
    """

    __tablename__ = "student_attempts"
    __table_args__ = (
        Index("ix_student_attempts_exam_student", "exam_id", "student_id"),
        Index("ix_student_attempts_is_latest", "exam_id", "student_id", "is_latest"),
    )

    exam_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exams.id"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_profiles.id"), nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="IN_PROGRESS"
    )  # IN_PROGRESS | SUBMITTED | AUTO_SUBMITTED | LOCKED
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_latest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    exam: Mapped["Exam"] = relationship(
        back_populates="attempts",
        lazy="raise",
    )
