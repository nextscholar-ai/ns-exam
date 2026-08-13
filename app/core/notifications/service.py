"""
Core Notification Engine & Dispatcher (Phase 19 §3).

Provides `NotificationDispatcher`:
  - Renders HTML/plain-text templates via `NotificationTemplateRegistry`.
  - Dispatches via transport channel (EMAIL, PUSH, MOCK).
  - Persists audit trail to DB via `NotificationLogRepository`.
  - Guarantees fire-and-forget isolation (dispatch failures never break transactions).
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import db_session_scope
from app.core.logging import get_logger
from app.core.notifications.templates import NotificationTemplateRegistry
from app.core.notifications.transports import (
    BaseTransport,
    TransportResult,
    get_email_transport,
    get_push_transport,
)

logger = get_logger(__name__)


class NotificationDispatcher:
    def __init__(
        self,
        email_transport: BaseTransport | None = None,
        push_transport: BaseTransport | None = None,
    ) -> None:
        self._email_transport = email_transport
        self._push_transport = push_transport

    def _get_transport(self, channel: str) -> BaseTransport:
        if channel.upper() == "EMAIL" and self._email_transport:
            return self._email_transport
        if channel.upper() == "PUSH" and self._push_transport:
            return self._push_transport
        if channel.upper() == "EMAIL":
            return get_email_transport()
        if channel.upper() == "PUSH":
            return get_push_transport()
        from app.core.notifications.transports import MockTransport
        return MockTransport()

    async def send_notification(
        self,
        notification_type: str,
        recipient_id: str,
        channel: str = "EMAIL",
        context: dict[str, Any] | None = None,
        recipient_type: str = "USER",
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        Main entry point for dispatching notifications.

        Steps:
          1. Render template context → subject, text_body, html_body.
          2. Create PENDING `NotificationLog` entry in DB (if DB available).
          3. Send via selected transport.
          4. Update `NotificationLog` status (SENT / MOCKED / FAILED).
        """
        ctx = context or {}
        rendered = NotificationTemplateRegistry.render(notification_type, ctx)
        log_id: int | None = None

        # 1. Create audit log (soft fail if DB not reachable/uninitialized)
        try:
            if session:
                from app.core.notifications.repository import NotificationLogRepository
                repo = NotificationLogRepository(session)
                log = await repo.create_log(
                    channel=channel.upper(),
                    notification_type=notification_type.upper(),
                    recipient_id=str(recipient_id),
                    recipient_type=recipient_type,
                    subject=rendered.subject,
                    body_preview=rendered.text_body,
                    status="PENDING",
                )
                log_id = log.id
            else:
                async with db_session_scope() as sess:
                    from app.core.notifications.repository import NotificationLogRepository
                    repo = NotificationLogRepository(sess)
                    log = await repo.create_log(
                        channel=channel.upper(),
                        notification_type=notification_type.upper(),
                        recipient_id=str(recipient_id),
                        recipient_type=recipient_type,
                        subject=rendered.subject,
                        body_preview=rendered.text_body,
                        status="PENDING",
                    )
                    log_id = log.id
        except Exception as exc:
            logger.warning(
                "notification.audit_log_create_failed",
                notification_type=notification_type,
                recipient_id=recipient_id,
                error=str(exc),
            )

        try:
            # 2. Dispatch transport
            transport = self._get_transport(channel)
            res: TransportResult = await transport.send(
                recipient=str(recipient_id),
                subject=rendered.subject,
                text_body=rendered.text_body,
                html_body=rendered.html_body,
                metadata={"notification_type": notification_type, **ctx},
            )

            # 3. Update audit log
            if log_id:
                try:
                    if session:
                        from app.core.notifications.repository import NotificationLogRepository
                        repo = NotificationLogRepository(session)
                        if res.status in ("SENT", "MOCKED"):
                            await repo.mark_sent(log_id, status=res.status)
                        else:
                            await repo.mark_failed(log_id, res.error_message or "Transport failed")
                    else:
                        async with db_session_scope() as sess:
                            from app.core.notifications.repository import NotificationLogRepository
                            repo = NotificationLogRepository(sess)
                            if res.status in ("SENT", "MOCKED"):
                                await repo.mark_sent(log_id, status=res.status)
                            else:
                                await repo.mark_failed(log_id, res.error_message or "Transport failed")
                except Exception as exc:
                    logger.warning("notification.audit_log_update_failed", error=str(exc))

            logger.info(
                "notification.dispatched",
                notification_type=notification_type,
                recipient_id=recipient_id,
                channel=channel,
                status=res.status,
            )
            return {
                "notification_type": notification_type,
                "recipient_id": recipient_id,
                "channel": channel,
                "status": res.status,
                "subject": rendered.subject,
            }

        except Exception as exc:
            logger.error(
                "notification.dispatch_failed",
                notification_type=notification_type,
                recipient_id=recipient_id,
                error=str(exc),
            )
            return {
                "notification_type": notification_type,
                "recipient_id": recipient_id,
                "channel": channel,
                "status": "FAILED",
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Backwards-compatible convenience helpers (Phase 18 interface)
    # ------------------------------------------------------------------

    async def send_report_ready(
        self,
        student_id: int,
        report_public_id: str,
        report_type: str = "STUDENT_REPORT_CARD",
        channel: str = "EMAIL",
        session: AsyncSession | None = None,
    ) -> None:
        await self.send_notification(
            notification_type="REPORT_READY",
            recipient_id=str(student_id),
            recipient_type="STUDENT",
            channel=channel,
            context={
                "student_id": student_id,
                "report_public_id": report_public_id,
                "report_type": report_type,
            },
            session=session,
        )

    async def send_at_risk_alert(
        self,
        student_id: int,
        teacher_id: int | None = None,
        subject_id: int | None = None,
        channel: str = "EMAIL",
        session: AsyncSession | None = None,
    ) -> None:
        recipient = str(teacher_id) if teacher_id else str(student_id)
        await self.send_notification(
            notification_type="STUDENT_AT_RISK",
            recipient_id=recipient,
            recipient_type="TEACHER" if teacher_id else "STUDENT",
            channel=channel,
            context={
                "student_id": student_id,
                "teacher_id": teacher_id,
                "subject_id": subject_id,
            },
            session=session,
        )

    async def send_job_completed(
        self,
        job_id: str,
        job_type: str,
        initiated_by: int | None = None,
        channel: str = "EMAIL",
        session: AsyncSession | None = None,
    ) -> None:
        recipient = str(initiated_by) if initiated_by else "system"
        await self.send_notification(
            notification_type="JOB_COMPLETED",
            recipient_id=recipient,
            recipient_type="USER" if initiated_by else "SYSTEM",
            channel=channel,
            context={
                "job_id": job_id,
                "job_type": job_type,
                "initiated_by": initiated_by,
            },
            session=session,
        )


# Global singleton dispatcher
notification_dispatcher = NotificationDispatcher()
