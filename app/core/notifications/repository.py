"""
Notification System — Repository Layer (Phase 19 §3).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.core.notifications.models import NotificationLog


class NotificationLogRepository(BaseRepository[NotificationLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NotificationLog)

    async def create_log(
        self,
        channel: str,
        notification_type: str,
        recipient_id: str,
        subject: str,
        recipient_type: str = "USER",
        body_preview: str | None = None,
        status: str = "PENDING",
    ) -> NotificationLog:
        """Create a new notification audit record."""
        log = NotificationLog(
            channel=channel,
            notification_type=notification_type,
            recipient_id=str(recipient_id),
            recipient_type=recipient_type,
            subject=subject,
            body_preview=body_preview[:500] if body_preview else None,
            status=status,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def mark_sent(self, log_id: int, status: str = "SENT") -> None:
        log = await self.get_by_id(log_id)
        if log:
            log.status = status
            log.sent_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def mark_failed(self, log_id: int, error_message: str) -> None:
        log = await self.get_by_id(log_id)
        if log:
            log.status = "FAILED"
            log.error_message = error_message[:1000]
            await self.session.flush()

    async def list_recent(
        self,
        limit: int = 50,
        channel: str | None = None,
        recipient_id: str | None = None,
    ) -> list[NotificationLog]:
        stmt = select(NotificationLog).where(NotificationLog.is_deleted.is_(False))
        if channel:
            stmt = stmt.where(NotificationLog.channel == channel)
        if recipient_id:
            stmt = stmt.where(NotificationLog.recipient_id == str(recipient_id))

        stmt = stmt.order_by(NotificationLog.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
