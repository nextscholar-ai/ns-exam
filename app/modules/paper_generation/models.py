"""
Paper Generation module — ORM models (Phase 11 §6.4–§6.6 & §6.8–§6.9).

Tables owned here:
  papers              — immutable aggregate root per exam/student.
  paper_sections      — section header rows inside a paper.
  paper_questions     — ordered question slots with polymorphic question ref.
  paper_versions      — immutable audit trail of every teacher edit.
  paper_validations   — per-rule validation result rows (§6.8).
  ai_generation_logs  — per-candidate explainability rows (§6.9).
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
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db.base_model import Base, BaseMixin

_JSON = JSONB().with_variant(JSON(), "sqlite")


class Paper(BaseMixin, Base):
    """
    Immutable aggregate root — one row per (exam_config, student) or
    (exam_config, NULL) for shared non-personalized papers (Phase 11 §6.4).

    Published papers are never mutated; edits create PaperVersion rows.
    """

    __tablename__ = "papers"
    __table_args__ = (
        Index(
            "ix_papers_exam_config_student",
            "exam_configuration_id",
            "student_id",
        ),
    )

    exam_configuration_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("exam_configurations.id"),
        nullable=False,
    )
    student_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("student_profiles.id"),
        nullable=True,
    )
    blueprint_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("blueprints.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="GENERATED"
    )
    total_marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    generated_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    sections: Mapped[list["PaperSection"]] = relationship(
        back_populates="paper",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="PaperSection.section_label",
    )
    versions: Mapped[list["PaperVersion"]] = relationship(
        back_populates="paper",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    validations: Mapped[list["PaperValidation"]] = relationship(
        back_populates="paper",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class PaperSection(BaseMixin, Base):
    """Header row for a section inside a paper (mirrors BlueprintSection)."""

    __tablename__ = "paper_sections"
    __table_args__ = (
        Index("ix_paper_sections_paper_id", "paper_id"),
    )

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    section_label: Mapped[str] = mapped_column(String(10), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section_marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    paper: Mapped["Paper"] = relationship(
        back_populates="sections",
        lazy="raise",
    )
    questions: Mapped[list["PaperQuestion"]] = relationship(
        back_populates="section",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="PaperQuestion.sequence_no",
    )


class PaperQuestion(BaseMixin, Base):
    """
    Ordered question slot inside a PaperSection.

    Polymorphic reference pattern (Phase 10 §6.2):
      question_type  — discriminator ('OBJECTIVE' | 'SUBJECTIVE' | 'FILL_BLANK')
      question_id    — FK value into the appropriate question table.

    selection_reason_json carries the per-criterion ranking scores for full
    explainability (Phase 11 §6.5 / §9).
    """

    __tablename__ = "paper_questions"
    __table_args__ = (
        Index("ix_paper_questions_section_id", "paper_section_id"),
    )

    paper_section_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_sections.id"), nullable=False
    )
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sequence_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    selection_reason_json: Mapped[dict | None] = mapped_column(
        _JSON, nullable=True
    )

    section: Mapped["PaperSection"] = relationship(
        back_populates="questions",
        lazy="raise",
    )


class PaperVersion(BaseMixin, Base):
    """
    Immutable audit trail of every teacher edit — snapshot-based (§6.6).

    Published papers (status=PUBLISHED) never get a new version; any re-edit
    requires an explicit admin unlock (logged in audit_logs).
    """

    __tablename__ = "paper_versions"
    __table_args__ = (
        Index("ix_paper_versions_paper_id", "paper_id"),
    )

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(_JSON, nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    paper: Mapped["Paper"] = relationship(
        back_populates="versions",
        lazy="raise",
    )


class PaperValidation(BaseMixin, Base):
    """
    Per-rule validation result (§6.8 rule set).

    rule_code examples:
      TOTAL_MARKS_MATCH, DURATION_VALID, SECTION_MARKS_MATCH,
      DIFFICULTY_BALANCE, BLOOM_COVERAGE, NO_DUPLICATE_QUESTIONS,
      CHAPTER_COVERAGE, QUESTION_AVAILABILITY
    """

    __tablename__ = "paper_validations"
    __table_args__ = (
        Index("ix_paper_validations_paper_id", "paper_id"),
    )

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    paper: Mapped["Paper"] = relationship(
        back_populates="validations",
        lazy="raise",
    )


class AIGenerationLog(BaseMixin, Base):
    """
    Explainability row per candidate question evaluated during generation (§6.9).

    Kept for both selected AND non-selected top-N candidates so
    'why wasn't question X picked?' is always answerable (audit/debug only).
    """

    __tablename__ = "ai_generation_logs"
    __table_args__ = (
        Index("ix_ai_generation_logs_paper_id", "paper_id"),
    )

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id"), nullable=False
    )
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    blueprint_match_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    difficulty_match_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    weak_topic_match_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    usage_balance_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    bloom_match_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    final_rank_score: Mapped[float] = mapped_column(
        Numeric(7, 4), nullable=False, default=0.0
    )
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
