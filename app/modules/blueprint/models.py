"""
Blueprint module — ORM models (Phase 11 §6.1–§6.3 & §6.7).

Tables owned here:
  blueprints            — top-level paper-structure rules (board-scoped).
  blueprint_sections    — per-section rules (question type, marks, count,
                          difficulty/bloom distributions).
  exam_configurations   — one exam config ties a blueprint to a session/type.
  student_papers        — assignment link (paper ↔ student ↔ exam); table is
                          owned here because it is paper-shaped data (§6.7).
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db.base_model import Base, BaseMixin

# ---------------------------------------------------------------------------
# SQLAlchemy dialect shim — use JSONB on Postgres, JSON on SQLite (tests).
# ---------------------------------------------------------------------------
_JSON = JSONB().with_variant(JSON(), "sqlite")


class Blueprint(BaseMixin, Base):
    """
    Defines the structural rules for a class of exam papers.

    Board-scoped aggregate root: one Blueprint may be reused across multiple
    ExamConfigurations (Phase 11 §6.1).
    """

    __tablename__ = "blueprints"
    __table_args__ = (
        Index("ix_blueprints_board_class_subject", "board_id", "class_id", "subject_id"),
    )

    board_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("boards.id"),
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    syllabus_coverage_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT"
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )

    sections: Mapped[list["BlueprintSection"]] = relationship(
        back_populates="blueprint",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    exam_configurations: Mapped[list["ExamConfiguration"]] = relationship(
        back_populates="blueprint",
        lazy="raise",
    )


class BlueprintSection(BaseMixin, Base):
    """
    Per-section question rules — rules only, no question references (§4).

    difficulty_distribution_json: {"EASY": 30, "MEDIUM": 50, "HARD": 20} (%)
    bloom_distribution_json:      {"REMEMBER": 20, "UNDERSTAND": 40, ...}  (%)
    chapter_scope_json:           [chapter_id, ...] — NULL means full blueprint scope.
    """

    __tablename__ = "blueprint_sections"
    __table_args__ = (
        Index("ix_blueprint_sections_blueprint_id", "blueprint_id"),
    )

    blueprint_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("blueprints.id"),
        nullable=False,
    )
    section_label: Mapped[str] = mapped_column(String(10), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section_marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty_distribution_json: Mapped[dict] = mapped_column(
        _JSON, nullable=False, default=dict
    )
    bloom_distribution_json: Mapped[dict | None] = mapped_column(
        _JSON, nullable=True
    )
    chapter_scope_json: Mapped[list | None] = mapped_column(
        _JSON, nullable=True
    )

    blueprint: Mapped["Blueprint"] = relationship(
        back_populates="sections",
        lazy="raise",
    )


class ExamConfiguration(BaseMixin, Base):
    """
    Ties a Blueprint to a specific academic session and exam type.

    exam_type:  REGULAR | MOCK  (Phase 1 §13 — no RECOVERY)
    personalized: when True, one Paper per student is generated.
    current_chapters_json / current_topics_json: teacher-narrowed scope for
    this exam, overrides blueprint's default chapter_scope_json per section.
    """

    __tablename__ = "exam_configurations"
    __table_args__ = (
        Index("ix_exam_configurations_blueprint_id", "blueprint_id"),
    )

    blueprint_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("blueprints.id"),
        nullable=False,
    )
    exam_name: Mapped[str] = mapped_column(String(255), nullable=False)
    academic_session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("academic_sessions.id"),
        nullable=False,
    )
    exam_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="REGULAR"
    )
    personalized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    current_chapters_json: Mapped[list | None] = mapped_column(
        _JSON, nullable=True
    )
    current_topics_json: Mapped[list | None] = mapped_column(
        _JSON, nullable=True
    )
    publish_date: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exam_date: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT"
    )

    blueprint: Mapped["Blueprint"] = relationship(
        back_populates="exam_configurations",
        lazy="raise",
    )


class StudentPaper(BaseMixin, Base):
    """
    Assignment link: one active paper per student per exam (Phase 11 §6.7).

    Unique constraint (exam_id, student_id) enforced at DB level via Index.
    paper_id FK resolves to papers.id owned by paper_generation module.
    """

    __tablename__ = "student_papers"
    __table_args__ = (
        Index(
            "uq_student_papers_exam_student",
            "exam_id",
            "student_id",
            unique=True,
        ),
    )

    # exam_id FK → exams.id resolved in Phase 12; kept nullable until then.
    exam_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("student_profiles.id"),
        nullable=False,
    )
