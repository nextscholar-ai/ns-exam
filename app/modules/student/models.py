"""
Student Profile module — ORM models (Phase 4 §6.3).

One table covers all three student types (ERP / External / Guest), discriminated
by `student_type` — matching Phase 1 §13's decision that Guest gets a real row
(needed for the 45-day report-retrieval window).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base_model import Base, BaseMixin


class StudentProfile(BaseMixin, Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        Index("ix_student_profiles_school_class", "school_id", "class_id"),
        Index("ix_student_profiles_student_type", "student_type"),
    )

    student_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ERP | EXTERNAL | GUEST
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    erp_student_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    roll_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    school_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("schools.id"), nullable=True
    )
    board_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("boards.id"), nullable=True)
    class_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("classes.id"), nullable=True)
    academic_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("academic_sessions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    # SnapshotMixin fields inlined manually (only meaningful for student_type='ERP';
    # not using full SnapshotMixin because erp_student_id above already carries the
    # unique ERP reference and this table isn't a pure ERP mirror like Academic Reference).
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False, default="SYNCED")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
