"""
ERP / SIS Integration module — Repository layer (Phase 18 §3).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.base_repository import BaseRepository
from app.modules.integration.models import SyncLog, compute_payload_hash


class SyncLogRepository(BaseRepository[SyncLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SyncLog)

    async def create(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> SyncLog:
        """Create a PENDING sync log entry."""
        log = SyncLog(
            event_name=event_name,
            payload_hash=compute_payload_hash(payload),
            status="PENDING",
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_by_payload_hash(self, payload_hash: str) -> SyncLog | None:
        """Return the most recent log with this payload hash (for deduplication)."""
        stmt = (
            select(SyncLog)
            .where(SyncLog.payload_hash == payload_hash)
            .order_by(SyncLog.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_sent(
        self, log_id: int, response_code: int, response_body: str
    ) -> None:
        log = await self.get_by_id(log_id)
        if log:
            log.status = "SENT"
            log.response_code = response_code
            log.response_body = response_body[:1000]
            log.synced_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def mark_failed(
        self, log_id: int, response_code: int, response_body: str
    ) -> None:
        log = await self.get_by_id(log_id)
        if log:
            log.status = "FAILED"
            log.response_code = response_code
            log.response_body = response_body[:1000]
            await self.session.flush()

    async def list_recent(self, limit: int = 50) -> list[SyncLog]:
        stmt = (
            select(SyncLog)
            .where(SyncLog.is_deleted.is_(False))
            .order_by(SyncLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
