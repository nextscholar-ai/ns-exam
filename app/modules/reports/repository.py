"""
Reporting Engine module — Repository layer (Phase 16 §8.5).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.reports.domain.state_machine import validate_report_transition
from app.modules.reports.models import ReportSnapshot


class ReportSnapshotRepository(BaseRepository[ReportSnapshot]):
    """Repository for ReportSnapshot aggregate root."""

    ALLOWED_SORT_FIELDS = {
        "created_at": ReportSnapshot.created_at,
        "report_type": ReportSnapshot.report_type,
    }

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ReportSnapshot)

    async def list_by_student(self, student_id: int) -> list[ReportSnapshot]:
        stmt = (
            select(ReportSnapshot)
            .where(ReportSnapshot.student_id == student_id)
            .where(ReportSnapshot.is_deleted == False)  # noqa: E712
            .order_by(ReportSnapshot.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_exam(self, exam_id: int) -> list[ReportSnapshot]:
        stmt = (
            select(ReportSnapshot)
            .where(ReportSnapshot.exam_id == exam_id)
            .where(ReportSnapshot.is_deleted == False)  # noqa: E712
            .order_by(ReportSnapshot.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def transition_status(
        self, report_id: int, target_status: str
    ) -> ReportSnapshot:
        """
        Enforce state machine status transition.
        """
        report = await self.get_or_raise(report_id)
        validate_report_transition(report.status, target_status)
        report.status = target_status
        await self.session.flush()
        return report
