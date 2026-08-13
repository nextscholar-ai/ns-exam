"""
Phase 19 — Notification Delivery System & Outbound Communication Unit Tests.

Tests cover:
  1. NotificationTemplateRegistry (template rendering for all notification types).
  2. NotificationLog model & NotificationLogRepository CRUD.
  3. Transports (MockTransport, EmailTransport dry-run, PushNotificationTransport dry-run).
  4. NotificationDispatcher integration with transports and DB logging.
  5. Backwards-compatible convenience methods (send_report_ready, send_at_risk_alert, send_job_completed).
  6. Notification Pydantic schemas.
"""
from __future__ import annotations

import pytest

from app.core.notifications.models import NotificationLog
from app.core.notifications.repository import NotificationLogRepository
from app.core.notifications.schemas import (
    NotificationLogResponse,
    NotificationTestRequest,
    NotificationTestResponse,
)
from app.core.notifications.service import NotificationDispatcher
from app.core.notifications.templates import NotificationTemplateRegistry, RenderedTemplate
from app.core.notifications.transports import (
    EmailTransport,
    MockTransport,
    PushNotificationTransport,
    TransportResult,
)


# ---------------------------------------------------------------------------
# 1. NotificationTemplateRegistry
# ---------------------------------------------------------------------------

def test_template_registry_report_ready():
    rendered = NotificationTemplateRegistry.render(
        "REPORT_READY",
        {"student_id": 42, "report_public_id": "rpt-99", "report_type": "Progress Report"},
    )
    assert isinstance(rendered, RenderedTemplate)
    assert "Progress Report" in rendered.subject
    assert "42" in rendered.text_body
    assert "rpt-99" in rendered.html_body


def test_template_registry_student_at_risk():
    rendered = NotificationTemplateRegistry.render(
        "STUDENT_AT_RISK",
        {"student_id": 7, "teacher_id": 3},
    )
    assert "7" in rendered.subject
    assert "at-risk" in rendered.text_body.lower()


def test_template_registry_job_completed():
    rendered = NotificationTemplateRegistry.render(
        "JOB_COMPLETED",
        {"job_id": "job-123", "job_type": "BULK_IMPORT"},
    )
    assert "BULK_IMPORT" in rendered.subject
    assert "job-123" in rendered.text_body


def test_template_registry_exam_published():
    rendered = NotificationTemplateRegistry.render(
        "EXAM_PUBLISHED",
        {"exam_public_id": "ex-001", "join_code": "JC123"},
    )
    assert "New Exam Published" in rendered.subject
    assert "JC123" in rendered.html_body


def test_template_registry_test_notification():
    rendered = NotificationTemplateRegistry.render(
        "TEST_NOTIFICATION",
        {"message": "Hello notification test"},
    )
    assert "Test Notification" in rendered.subject
    assert "Hello notification test" in rendered.text_body


def test_template_registry_unknown_type_fallback():
    rendered = NotificationTemplateRegistry.render(
        "UNKNOWN_TYPE",
        {"message": "Custom fallback message"},
    )
    assert rendered.subject == "System Notification"
    assert "Custom fallback message" in rendered.text_body


# ---------------------------------------------------------------------------
# 2. NotificationLog model & NotificationLogRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notification_log_created(sqlite_session):
    repo = NotificationLogRepository(sqlite_session)
    log = await repo.create_log(
        channel="EMAIL",
        notification_type="REPORT_READY",
        recipient_id="user@example.com",
        recipient_type="STUDENT",
        subject="Your Report is Ready",
        body_preview="Body summary text",
    )
    await sqlite_session.flush()

    assert log.id is not None
    assert log.public_id is not None
    assert log.channel == "EMAIL"
    assert log.status == "PENDING"
    assert log.recipient_id == "user@example.com"


@pytest.mark.asyncio
async def test_notification_log_mark_sent(sqlite_session):
    repo = NotificationLogRepository(sqlite_session)
    log = await repo.create_log(
        channel="PUSH",
        notification_type="STUDENT_AT_RISK",
        recipient_id="device-token-123",
        subject="Alert",
    )
    await sqlite_session.flush()

    await repo.mark_sent(log.id, status="SENT")
    await sqlite_session.refresh(log)

    assert log.status == "SENT"
    assert log.sent_at is not None


@pytest.mark.asyncio
async def test_notification_log_mark_failed(sqlite_session):
    repo = NotificationLogRepository(sqlite_session)
    log = await repo.create_log(
        channel="EMAIL",
        notification_type="JOB_COMPLETED",
        recipient_id="user@example.com",
        subject="Job Status",
    )
    await sqlite_session.flush()

    await repo.mark_failed(log.id, "SMTP Connection Refused")
    await sqlite_session.refresh(log)

    assert log.status == "FAILED"
    assert log.error_message == "SMTP Connection Refused"


@pytest.mark.asyncio
async def test_notification_log_list_recent_filtering(sqlite_session):
    repo = NotificationLogRepository(sqlite_session)
    await repo.create_log(channel="EMAIL", notification_type="T1", recipient_id="u1", subject="S1")
    await repo.create_log(channel="PUSH", notification_type="T2", recipient_id="u2", subject="S2")
    await repo.create_log(channel="EMAIL", notification_type="T3", recipient_id="u1", subject="S3")
    await sqlite_session.flush()

    email_logs = await repo.list_recent(channel="EMAIL")
    assert len(email_logs) == 2

    u1_logs = await repo.list_recent(recipient_id="u1")
    assert len(u1_logs) == 2


# ---------------------------------------------------------------------------
# 3. Transports
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_transport_records_messages():
    transport = MockTransport()
    res = await transport.send(
        recipient="user-123",
        subject="Test Subject",
        text_body="Text Body",
        html_body="<p>HTML Body</p>",
    )
    assert res.status == "MOCKED"
    assert len(transport.sent_messages) == 1
    assert transport.sent_messages[0]["recipient"] == "user-123"


@pytest.mark.asyncio
async def test_email_transport_dry_run_when_disabled():
    transport = EmailTransport(enabled=False, host="")
    res = await transport.send(
        recipient="test@example.com",
        subject="Test",
        text_body="Text",
        html_body="HTML",
    )
    assert res.status == "MOCKED"
    assert res.channel == "EMAIL"


@pytest.mark.asyncio
async def test_push_transport_dry_run_when_disabled():
    transport = PushNotificationTransport(enabled=False, gateway_url="")
    res = await transport.send(
        recipient="device-token",
        subject="Push Title",
        text_body="Push Body",
        html_body="<p>Push Body</p>",
    )
    assert res.status == "MOCKED"
    assert res.channel == "PUSH"


# ---------------------------------------------------------------------------
# 4. NotificationDispatcher
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatcher_send_notification_mock_transport():
    mock_email = MockTransport(default_status="SENT")
    dispatcher = NotificationDispatcher(email_transport=mock_email)

    res = await dispatcher.send_notification(
        notification_type="REPORT_READY",
        recipient_id="student-100",
        channel="EMAIL",
        context={"student_id": 100, "report_public_id": "rpt-100"},
    )

    assert res["status"] == "SENT"
    assert res["notification_type"] == "REPORT_READY"
    assert len(mock_email.sent_messages) == 1


@pytest.mark.asyncio
async def test_dispatcher_send_report_ready_convenience_method():
    mock_email = MockTransport(default_status="SENT")
    dispatcher = NotificationDispatcher(email_transport=mock_email)

    await dispatcher.send_report_ready(
        student_id=55,
        report_public_id="rpt-55",
        report_type="STUDENT_REPORT_CARD",
    )

    assert len(mock_email.sent_messages) == 1
    assert mock_email.sent_messages[0]["recipient"] == "55"


@pytest.mark.asyncio
async def test_dispatcher_send_at_risk_alert_convenience_method():
    mock_email = MockTransport(default_status="SENT")
    dispatcher = NotificationDispatcher(email_transport=mock_email)

    await dispatcher.send_at_risk_alert(
        student_id=88,
        teacher_id=12,
    )

    assert len(mock_email.sent_messages) == 1
    assert mock_email.sent_messages[0]["recipient"] == "12"


@pytest.mark.asyncio
async def test_dispatcher_send_job_completed_convenience_method():
    mock_email = MockTransport(default_status="SENT")
    dispatcher = NotificationDispatcher(email_transport=mock_email)

    await dispatcher.send_job_completed(
        job_id="job-999",
        job_type="BULK_QUESTION_IMPORT",
        initiated_by=7,
    )

    assert len(mock_email.sent_messages) == 1
    assert mock_email.sent_messages[0]["recipient"] == "7"


@pytest.mark.asyncio
async def test_dispatcher_creates_db_notification_log(sqlite_session):
    mock_email = MockTransport(default_status="SENT")
    dispatcher = NotificationDispatcher(email_transport=mock_email)

    res = await dispatcher.send_notification(
        notification_type="REPORT_READY",
        recipient_id="student-200",
        channel="EMAIL",
        context={"student_id": 200, "report_public_id": "rpt-200"},
        session=sqlite_session,
    )

    assert res["status"] == "SENT"
    repo = NotificationLogRepository(sqlite_session)
    logs = await repo.list_recent(recipient_id="student-200")
    assert len(logs) == 1
    assert logs[0].notification_type == "REPORT_READY"
    assert logs[0].status == "SENT"


# ---------------------------------------------------------------------------
# 5. Pydantic Schemas
# ---------------------------------------------------------------------------

def test_notification_schemas_valid():
    req = NotificationTestRequest(
        recipient_id="test@domain.com",
        notification_type="TEST_NOTIFICATION",
        channel="EMAIL",
    )
    assert req.recipient_id == "test@domain.com"
    assert req.channel == "EMAIL"

    resp = NotificationTestResponse(
        notification_type="TEST_NOTIFICATION",
        recipient_id="test@domain.com",
        channel="EMAIL",
        status="MOCKED",
        subject="Test Notification",
    )
    assert resp.status == "MOCKED"
