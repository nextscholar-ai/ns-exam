"""Teacher Profile module — ORM models (Phase 4 §6.3)."""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base_model import Base, SnapshotMixin


class TeacherProfile(SnapshotMixin, Base):
    __tablename__ = "teacher_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    erp_teacher_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("schools.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class TeacherSubjectMap(Base):
    """Teacher <-> Subject many-to-many ("Subject Mapping"). Composite PK,
    no BaseMixin - pure association table."""

    __tablename__ = "teacher_subject_map"

    teacher_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teacher_profiles.id"), primary_key=True
    )
    subject_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subjects.id"), primary_key=True
    )
