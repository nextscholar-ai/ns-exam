"""
Notification System — Router (Phase 19 §3).

Endpoints:
  GET  /notifications/logs  — List recent notification delivery audit logs.
  POST /notifications/test  — Trigger test notification dispatch.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_db
from app.core.notifications.repository import NotificationLogRepository
from app.core.notifications.schemas import (
    NotificationLogResponse,
    NotificationTestRequest,
    NotificationTestResponse,
)
from app.core.notifications.service import notification_dispatcher

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "/logs",
    response_model=list[NotificationLogResponse],
    summary="List recent notification audit log entries",
)
async def list_notification_logs(
    limit: int = 50,
    channel: str | None = None,
    recipient_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[NotificationLogResponse]:
    repo = NotificationLogRepository(db)
    logs = await repo.list_recent(limit=limit, channel=channel, recipient_id=recipient_id)

    return [
        NotificationLogResponse(
            id=str(log.public_id),
            channel=log.channel,
            notification_type=log.notification_type,
            recipient_id=log.recipient_id,
            recipient_type=log.recipient_type,
            status=log.status,
            subject=log.subject,
            body_preview=log.body_preview,
            error_message=log.error_message,
            sent_at=log.sent_at.isoformat() if log.sent_at else None,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.post(
    "/test",
    response_model=NotificationTestResponse,
    summary="Trigger a test notification dispatch",
)
async def send_test_notification(
    body: NotificationTestRequest,
) -> NotificationTestResponse:
    res = await notification_dispatcher.send_notification(
        notification_type=body.notification_type,
        recipient_id=body.recipient_id,
        channel=body.channel,
        context=body.context,
    )
    return NotificationTestResponse(**res)
