"""
Question Bank module - ORM models.

Implements Phase 10 Database Design:
  - Three distinct question type tables: objective, subjective, fill-in-blank.
  - Polymorphic QuestionVersion snapshot table.
  - QuestionFile attachment table.
  - QuestionStatistics performance & AI-ranking metrics table.
  - Secondary chapter/unit/topic mapping tables.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import app.modules.storage.models  # noqa: F401


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

# Cross-dialect JSON column
JSONColumn = JSONB().with_variant(JSON(), "sqlite")


class ObjectiveQuestion(Base, BaseMixin):
    """Multiple-choice objective question model."""

    __tablename__ = "objective_questions"

    question_group_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    board_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("boards.id"),
        nullable=False,
        index=True,
    )
    class_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("classes.id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subjects.id"),
        nullable=False,
        index=True,
    )
    primary_chapter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chapters.id"),
        nullable=False,
        index=True,
    )
    primary_unit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("units.id"),
        nullable=True,
    )
    primary_topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("topics.id"),
        nullable=True,
    )
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONColumn,
        nullable=False,
    )
    correct_option: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    explanation_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    difficulty: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        index=True,
    )
    bloom_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="UNDERSTAND",
        index=True,
    )
    marks: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=1.0,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        index=True,
    )
    version_no: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )


class SubjectiveQuestion(Base, BaseMixin):
    """Short and long answer subjective question model."""

    __tablename__ = "subjective_questions"

    question_group_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    board_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("boards.id"),
        nullable=False,
        index=True,
    )
    class_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("classes.id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subjects.id"),
        nullable=False,
        index=True,
    )
    primary_chapter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chapters.id"),
        nullable=False,
        index=True,
    )
    primary_unit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("units.id"),
        nullable=True,
    )
    primary_topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("topics.id"),
        nullable=True,
    )
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    model_answer_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    max_marks: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=5.0,
    )
    expected_key_points_json: Mapped[list[str] | None] = mapped_column(
        JSONColumn,
        nullable=True,
    )
    difficulty: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        index=True,
    )
    bloom_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ANALYZE",
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        index=True,
    )
    version_no: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )


class FillBlankQuestion(Base, BaseMixin):
    """Fill-in-the-blank question model."""

    __tablename__ = "fill_blank_questions"

    question_group_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    board_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("boards.id"),
        nullable=False,
        index=True,
    )
    class_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("classes.id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subjects.id"),
        nullable=False,
        index=True,
    )
    primary_chapter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chapters.id"),
        nullable=False,
        index=True,
    )
    primary_unit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("units.id"),
        nullable=True,
    )
    primary_topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("topics.id"),
        nullable=True,
    )
    question_text_with_blanks: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    correct_answers_json: Mapped[list[str]] = mapped_column(
        JSONColumn,
        nullable=False,
    )
    marks: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=1.0,
    )
    difficulty: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="EASY",
        index=True,
    )
    bloom_level: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="REMEMBER",
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        index=True,
    )
    version_no: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )


class QuestionVersion(Base, BaseMixin):
    """Polymorphic question snapshot version model."""

    __tablename__ = "question_versions"

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONColumn,
        nullable=False,
    )
    change_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class QuestionFile(Base, BaseMixin):
    """File attachment mapping model."""

    __tablename__ = "question_files"

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    file_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("files.id"),
        nullable=False,
    )
    file_role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ATTACHMENT",
    )


class QuestionStatistics(Base, BaseMixin):
    """Performance statistics and AI ranking input model."""

    __tablename__ = "question_statistics"

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    usage_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    correct_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    wrong_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    correct_percentage: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=0.0,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paper_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    student_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    difficulty_trend_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONColumn,
        nullable=True,
    )


class QuestionChapterMap(Base, BaseMixin):
    """Secondary chapter mapping model."""

    __tablename__ = "question_chapter_map"

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    chapter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chapters.id"),
        nullable=False,
    )


class QuestionUnitMap(Base, BaseMixin):
    """Secondary unit mapping model."""

    __tablename__ = "question_unit_map"

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("units.id"),
        nullable=False,
    )


class QuestionTopicMap(Base, BaseMixin):
    """Secondary topic mapping model."""

    __tablename__ = "question_topic_map"

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    topic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("topics.id"),
        nullable=False,
    )
