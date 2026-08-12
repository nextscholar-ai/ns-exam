"""
Academic Reference module — ORM models (Phase 4 §6.2).

Every table here is ERP-owned, read-only-from-Exam-Engine snapshot data
(`SnapshotMixin`). Never mutated by user-facing API — only by the ERP sync
job (Phase 16/17). Aggregate root: `Board`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base_model import Base, SnapshotMixin


class Board(SnapshotMixin, Base):
    __tablename__ = "boards"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    schools: Mapped[list["School"]] = relationship(back_populates="board", lazy="raise")


class School(SnapshotMixin, Base):
    __tablename__ = "schools"
    __table_args__ = (Index("ix_schools_board_id", "board_id"),)

    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("boards.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    board: Mapped["Board"] = relationship(back_populates="schools", lazy="raise")


class AcademicSession(SnapshotMixin, Base):
    __tablename__ = "academic_sessions"

    school_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("schools.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "2026-27"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Class(SnapshotMixin, Base):
    __tablename__ = "classes"

    school_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("schools.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "Class 10"


class Subject(SnapshotMixin, Base):
    __tablename__ = "subjects"
    __table_args__ = (Index("ix_subjects_board_class", "board_id", "class_id"),)

    board_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("boards.id"), nullable=False
    )
    class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("classes.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Chapter(SnapshotMixin, Base):
    __tablename__ = "chapters"

    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class Unit(SnapshotMixin, Base):
    __tablename__ = "units"

    chapter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chapters.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Topic(SnapshotMixin, Base):
    __tablename__ = "topics"

    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("units.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
