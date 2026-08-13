"""
Notification System — Transport Adapters (Phase 19 §3).

Provides:
  - `TransportResult`: Status dataclass returned by all transport calls.
  - `BaseTransport`: Abstract transport interface.
  - `EmailTransport`: SMTP email dispatcher (mock dry-run when unconfigured).
  - `PushNotificationTransport`: HTTP Push notification gateway adapter.
  - `MockTransport`: In-process test double recording sent payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TransportResult:
    status: str  # SENT | FAILED | MOCKED
    channel: str
    error_message: str | None = None
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseTransport:
    async def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransportResult:
        raise NotImplementedError


class MockTransport(BaseTransport):
    """Test double recording sent notifications in memory."""

    def __init__(self, default_status: str = "MOCKED") -> None:
        self.default_status = default_status
        self.sent_messages: list[dict[str, Any]] = []

    async def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransportResult:
        self.sent_messages.append({
            "recipient": recipient,
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body,
            "metadata": metadata or {},
        })
        logger.info("transport.mock.sent", recipient=recipient, subject=subject)
        return TransportResult(status=self.default_status, channel="MOCK")


class EmailTransport(BaseTransport):
    """
    SMTP Email transport.

    If SMTP settings (`host`/`user`) are empty or `email_enabled` is False,
    operates in dry-run mode (`MOCKED`), logging the email without raising.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 587,
        user: str = "",
        password: str = "",
        from_email: str = "notifications@ns-exam.com",
        enabled: bool = False,
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_email = from_email
        self.enabled = enabled
        self.use_tls = use_tls

    async def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransportResult:
        if not self.enabled or not self.host:
            logger.info(
                "transport.email.dry_run",
                recipient=recipient,
                subject=subject,
                enabled=self.enabled,
            )
            return TransportResult(status="MOCKED", channel="EMAIL")

        try:
            import asyncio
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            def _send_sync() -> None:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = self.from_email
                msg["To"] = recipient

                msg.attach(MIMEText(text_body, "plain"))
                msg.attach(MIMEText(html_body, "html"))

                with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                    if self.use_tls:
                        server.starttls()
                    if self.user and self.password:
                        server.login(self.user, self.password)
                    server.sendmail(self.from_email, [recipient], msg.as_string())

            await asyncio.to_thread(_send_sync)
            logger.info("transport.email.sent", recipient=recipient, subject=subject)
            return TransportResult(status="SENT", channel="EMAIL")

        except Exception as exc:
            logger.error("transport.email.failed", recipient=recipient, error=str(exc))
            return TransportResult(status="FAILED", channel="EMAIL", error_message=str(exc))


class PushNotificationTransport(BaseTransport):
    """
    HTTP Push Notification Gateway transport (FCM/WebPush model).

    If gateway URL is empty or `push_enabled` is False, logs dry-run (`MOCKED`).
    """

    def __init__(
        self,
        gateway_url: str = "",
        api_key: str = "",
        enabled: bool = False,
    ) -> None:
        self.gateway_url = gateway_url
        self.api_key = api_key
        self.enabled = enabled

    async def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        metadata: dict[str, Any] | None = None,
    ) -> TransportResult:
        if not self.enabled or not self.gateway_url:
            logger.info(
                "transport.push.dry_run",
                recipient=recipient,
                subject=subject,
                enabled=self.enabled,
            )
            return TransportResult(status="MOCKED", channel="PUSH")

        try:
            import httpx

            payload = {
                "recipient": recipient,
                "title": subject,
                "body": text_body,
                "data": metadata or {},
            }
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self.gateway_url, json=payload, headers=headers)

            if resp.is_success:
                logger.info("transport.push.sent", recipient=recipient, title=subject)
                return TransportResult(status="SENT", channel="PUSH")
            else:
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error("transport.push.failed", recipient=recipient, error=err)
                return TransportResult(status="FAILED", channel="PUSH", error_message=err)

        except Exception as exc:
            logger.error("transport.push.exception", recipient=recipient, error=str(exc))
            return TransportResult(status="FAILED", channel="PUSH", error_message=str(exc))


def get_email_transport() -> EmailTransport:
    from app.core.config import settings

    return EmailTransport(
        host=settings.notification.smtp_host,
        port=settings.notification.smtp_port,
        user=settings.notification.smtp_user,
        password=settings.notification.smtp_password,
        from_email=settings.notification.smtp_from_email,
        enabled=settings.notification.email_enabled,
        use_tls=settings.notification.smtp_use_tls,
    )


def get_push_transport() -> PushNotificationTransport:
    from app.core.config import settings

    return PushNotificationTransport(
        gateway_url=settings.notification.push_gateway_url,
        api_key=settings.notification.push_api_key,
        enabled=settings.notification.push_enabled,
    )
