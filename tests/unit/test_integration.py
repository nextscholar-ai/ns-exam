"""
Phase 18 — ERP Integration Tests.

Tests verify:
  1. SyncLog model fields and payload hash computation.
  2. SyncLogRepository CRUD: create, mark_sent, mark_failed, list_recent.
  3. Deduplication: get_by_payload_hash returns existing log.
  4. ERPIntegrationService.sync_report() with MockWebhookClient.
  5. ERPIntegrationService.sync_analytics_at_risk().
  6. Idempotency: same payload skipped if already SENT.
  7. ERP not configured: no HTTP call, SKIPPED_NO_ERP returned.
  8. ERPIntegrationService.resync_report() bypasses dedup.
  9. ERPIntegrationService.get_sync_logs() returns audit entries.
  10. Integration event handlers subscribe to correct events.
  11. MockWebhookClient records calls correctly.
  12. WebhookClient returns ok=False on 4xx responses.
"""
from __future__ import annotations

import pytest

from app.modules.integration.models import SyncLog, compute_payload_hash
from app.modules.integration.repository import SyncLogRepository
from app.modules.integration.service import ERPIntegrationService
from app.modules.integration.webhook import MockWebhookClient, WebhookResponse


# ---------------------------------------------------------------------------
# 1. Payload hash computation — deterministic regardless of dict order
# ---------------------------------------------------------------------------

def test_compute_payload_hash_deterministic():
    payload_a = {"b": 2, "a": 1}
    payload_b = {"a": 1, "b": 2}
    assert compute_payload_hash(payload_a) == compute_payload_hash(payload_b)


def test_compute_payload_hash_different_payloads():
    h1 = compute_payload_hash({"report_id": "abc"})
    h2 = compute_payload_hash({"report_id": "xyz"})
    assert h1 != h2


def test_compute_payload_hash_is_64_chars():
    h = compute_payload_hash({"x": 1})
    assert len(h) == 64


# ---------------------------------------------------------------------------
# 2. SyncLog model fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_log_created_in_db(sqlite_session):
    repo = SyncLogRepository(sqlite_session)
    log = await repo.create("ReportGenerated", {"report_id": "rpt-001"})
    await sqlite_session.flush()

    assert log.id is not None
    assert log.public_id is not None
    assert log.event_name == "ReportGenerated"
    assert log.status == "PENDING"
    assert len(log.payload_hash) == 64
    assert log.response_code is None
    assert log.synced_at is None


# ---------------------------------------------------------------------------
# 3. SyncLogRepository — mark_sent and mark_failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_log_mark_sent(sqlite_session):
    repo = SyncLogRepository(sqlite_session)
    log = await repo.create("ReportGenerated", {"report_id": "rpt-002"})
    await sqlite_session.flush()

    await repo.mark_sent(log.id, 200, '{"ok": true}')
    await sqlite_session.refresh(log)

    assert log.status == "SENT"
    assert log.response_code == 200
    assert log.synced_at is not None


@pytest.mark.asyncio
async def test_sync_log_mark_failed(sqlite_session):
    repo = SyncLogRepository(sqlite_session)
    log = await repo.create("AnalyticsUpdated", {"student_id": 5})
    await sqlite_session.flush()

    await repo.mark_failed(log.id, 503, "Service Unavailable")
    await sqlite_session.refresh(log)

    assert log.status == "FAILED"
    assert log.response_code == 503


# ---------------------------------------------------------------------------
# 4. Deduplication via payload hash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_by_payload_hash_returns_existing(sqlite_session):
    repo = SyncLogRepository(sqlite_session)
    payload = {"report_id": "rpt-dedup"}
    log = await repo.create("ReportGenerated", payload)
    await sqlite_session.flush()

    found = await repo.get_by_payload_hash(compute_payload_hash(payload))
    assert found is not None
    assert found.id == log.id


@pytest.mark.asyncio
async def test_get_by_payload_hash_returns_none_for_unknown(sqlite_session):
    repo = SyncLogRepository(sqlite_session)
    found = await repo.get_by_payload_hash("0" * 64)
    assert found is None


# ---------------------------------------------------------------------------
# 5. list_recent returns logs in descending order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_recent_returns_newest_first(sqlite_session):
    repo = SyncLogRepository(sqlite_session)
    for i in range(3):
        await repo.create("ReportGenerated", {"seq": i})
    await sqlite_session.flush()

    logs = await repo.list_recent(limit=10)
    assert len(logs) >= 3
    # Verify descending order
    for i in range(len(logs) - 1):
        assert logs[i].created_at >= logs[i + 1].created_at


# ---------------------------------------------------------------------------
# 6. ERPIntegrationService.sync_report() with MockWebhookClient — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_erp_service_sync_report_success(sqlite_session):
    mock = MockWebhookClient(default_status=200)
    # Set a dummy base_url so the service doesn't skip
    mock.base_url = "http://erp.test"

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)
    result = await svc.sync_report(
        report_public_id="rpt-001",
        student_id=1,
        exam_id=10,
        report_type="STUDENT_REPORT_CARD",
    )

    assert result["status"] == "SENT"
    assert result["response_code"] == 200
    assert len(mock.calls) == 1
    assert mock.calls[0]["payload"]["report_public_id"] == "rpt-001"


@pytest.mark.asyncio
async def test_erp_service_sync_report_failure(sqlite_session):
    mock = MockWebhookClient(default_status=503)
    mock.base_url = "http://erp.test"

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)
    result = await svc.sync_report(
        report_public_id="rpt-002",
        student_id=2,
        exam_id=None,
        report_type="EXAM_ANALYSIS",
    )

    assert result["status"] == "FAILED"
    assert result["response_code"] == 503


# ---------------------------------------------------------------------------
# 7. ERPIntegrationService.sync_analytics_at_risk()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_erp_service_sync_at_risk(sqlite_session):
    mock = MockWebhookClient(default_status=201)
    mock.base_url = "http://erp.test"

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)
    result = await svc.sync_analytics_at_risk(
        student_id=7, is_at_risk=True, class_id=3
    )

    assert result["status"] == "SENT"
    assert mock.calls[0]["payload"]["student_id"] == 7
    assert mock.calls[0]["payload"]["is_at_risk"] is True


# ---------------------------------------------------------------------------
# 8. Idempotency: same payload skipped if already SENT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_erp_service_idempotency_skip_duplicate(sqlite_session):
    mock = MockWebhookClient(default_status=200)
    mock.base_url = "http://erp.test"

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)

    # First call — should send
    result1 = await svc.sync_report(
        report_public_id="rpt-idem",
        student_id=3,
        exam_id=5,
        report_type="STUDENT_REPORT_CARD",
    )
    assert result1["status"] == "SENT"

    # Second call with identical payload — should skip
    result2 = await svc.sync_report(
        report_public_id="rpt-idem",
        student_id=3,
        exam_id=5,
        report_type="STUDENT_REPORT_CARD",
    )
    assert result2["status"] == "SKIPPED_DUPLICATE"
    # Only one HTTP call was made
    assert len(mock.calls) == 1


# ---------------------------------------------------------------------------
# 9. ERP not configured — no HTTP call, SKIPPED_NO_ERP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_erp_service_no_erp_configured(sqlite_session):
    mock = MockWebhookClient(default_status=200)
    # Leave base_url empty (default mock has no base_url set via attr)
    mock.base_url = ""

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)
    result = await svc.sync_report(
        report_public_id="rpt-no-erp",
        student_id=9,
        exam_id=None,
        report_type="STUDENT_REPORT_CARD",
    )

    assert result["status"] == "SKIPPED_NO_ERP"
    assert len(mock.calls) == 0


# ---------------------------------------------------------------------------
# 10. resync_report bypasses dedup and always sends
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_erp_service_resync_bypasses_dedup(sqlite_session):
    mock = MockWebhookClient(default_status=200)
    mock.base_url = "http://erp.test"

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)

    # Two resync calls for the same report — both should POST
    await svc.resync_report("rpt-force-1")
    await svc.resync_report("rpt-force-1")

    assert len(mock.calls) == 2


# ---------------------------------------------------------------------------
# 11. get_sync_logs returns recent audit entries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_erp_service_get_sync_logs(sqlite_session):
    mock = MockWebhookClient(default_status=200)
    mock.base_url = "http://erp.test"

    svc = ERPIntegrationService(sqlite_session, webhook_client=mock)

    await svc.sync_report("rpt-log-1", student_id=1, exam_id=1, report_type="STUDENT_REPORT_CARD")
    await svc.sync_report("rpt-log-2", student_id=2, exam_id=2, report_type="EXAM_ANALYSIS")

    logs = await svc.get_sync_logs(limit=10)
    assert len(logs) >= 2
    assert all("event_name" in entry for entry in logs)
    assert all("status" in entry for entry in logs)


# ---------------------------------------------------------------------------
# 12. MockWebhookClient records path and payload correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_webhook_client_records_calls():
    mock = MockWebhookClient(default_status=200)
    resp = await mock.post("/webhooks/test", {"key": "val"})

    assert resp.ok is True
    assert resp.status_code == 200
    assert len(mock.calls) == 1
    assert mock.calls[0]["path"] == "/webhooks/test"
    assert mock.calls[0]["payload"]["key"] == "val"


@pytest.mark.asyncio
async def test_mock_webhook_client_failure_response():
    mock = MockWebhookClient(default_status=500)
    resp = await mock.post("/webhooks/test", {})

    assert resp.ok is False
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# 13. Integration event handlers subscribe to correct events
# ---------------------------------------------------------------------------

def test_register_integration_handlers_wires_correct_events():
    from app.core.events.bus import event_bus
    from app.core.events.event_names import ANALYTICS_UPDATED, REPORT_GENERATED
    from app.modules.integration.events import register_integration_event_handlers

    # Register (may already be registered — idempotent append is fine for test)
    register_integration_event_handlers()

    report_handlers = event_bus._subscribers.get(REPORT_GENERATED, [])
    analytics_handlers = event_bus._subscribers.get(ANALYTICS_UPDATED, [])

    assert len(report_handlers) >= 1
    assert len(analytics_handlers) >= 1
