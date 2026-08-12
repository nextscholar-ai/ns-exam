"""
Phase 17 — Event Bus Integration Tests.

Tests verify:
  1. EventBus subscribe/publish round-trip (async handlers receive payloads).
  2. Handler isolation: a failing handler does NOT prevent other handlers from running.
  3. retry_async_job exponential backoff retries on transient errors.
  4. retry_async_job raises after max retries.
  5. All module events.py publish functions dispatch to the real bus.
  6. register_all_handlers wires expected subscribers.
"""
from __future__ import annotations

import asyncio
import pytest

from app.core.events.bus import EventBus, event_bus
from app.core.events.event_names import (
    ANALYTICS_UPDATED,
    EVALUATION_COMPLETED,
    EXAM_PUBLISHED,
    EXAM_SUBMITTED,
    LEARNING_PROFILE_UPDATED,
    MASTERY_UPDATED,
    PAPER_APPROVED,
    PAPER_GENERATED,
    QUESTION_IMPORTED,
    RECOMMENDATION_GENERATED,
    REPORT_GENERATED,
)
from app.core.events.retry import retry_async_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Collector:
    """Accumulates all payloads received by a handler."""
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, payload: dict) -> None:
        self.calls.append(payload)


# ---------------------------------------------------------------------------
# 1. Basic Pub/Sub
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_bus_single_subscriber():
    bus = EventBus()
    collector = _Collector()

    bus.subscribe("TestEvent", collector)
    await bus.publish("TestEvent", {"key": "value"})

    assert len(collector.calls) == 1
    assert collector.calls[0] == {"key": "value"}


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers_same_event():
    bus = EventBus()
    c1, c2 = _Collector(), _Collector()

    bus.subscribe("Evt", c1)
    bus.subscribe("Evt", c2)
    await bus.publish("Evt", {"x": 1})

    assert len(c1.calls) == 1
    assert len(c2.calls) == 1


@pytest.mark.asyncio
async def test_event_bus_no_subscribers_is_a_noop():
    """Publishing to an unsubscribed event should not raise."""
    bus = EventBus()
    await bus.publish("NoOneListens", {"data": 42})  # must not raise


@pytest.mark.asyncio
async def test_event_bus_multiple_events_isolated():
    bus = EventBus()
    c_a, c_b = _Collector(), _Collector()

    bus.subscribe("EventA", c_a)
    bus.subscribe("EventB", c_b)

    await bus.publish("EventA", {"src": "a"})
    await bus.publish("EventB", {"src": "b"})

    assert len(c_a.calls) == 1 and c_a.calls[0]["src"] == "a"
    assert len(c_b.calls) == 1 and c_b.calls[0]["src"] == "b"


# ---------------------------------------------------------------------------
# 2. Handler Isolation — a failing handler must not block subsequent handlers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_bus_failing_handler_isolated():
    bus = EventBus()
    good = _Collector()

    async def bad_handler(payload: dict) -> None:
        raise RuntimeError("boom!")

    bus.subscribe("IsoEvent", bad_handler)
    bus.subscribe("IsoEvent", good)

    # Should NOT raise
    await bus.publish("IsoEvent", {"data": "test"})

    # good handler still ran
    assert len(good.calls) == 1


@pytest.mark.asyncio
async def test_event_bus_all_failing_handlers_does_not_raise():
    bus = EventBus()

    async def always_fails(payload: dict) -> None:
        raise ValueError("always")

    bus.subscribe("FailAll", always_fails)
    bus.subscribe("FailAll", always_fails)

    # Publisher must absorb all failures
    await bus.publish("FailAll", {})


# ---------------------------------------------------------------------------
# 3. retry_async_job — success on first try
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_async_job_succeeds_immediately():
    async def my_job(x: int) -> int:
        return x * 2

    result = await retry_async_job(my_job, 5)
    assert result == 10


# ---------------------------------------------------------------------------
# 4. retry_async_job — retries on transient failure then succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_async_job_retries_then_succeeds():
    call_count = 0

    async def flaky(target: int) -> int:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("transient")
        return target

    result = await retry_async_job(
        flaky, 99,
        max_retries=3,
        initial_delay_sec=0.0,
    )
    assert result == 99
    assert call_count == 3


# ---------------------------------------------------------------------------
# 5. retry_async_job — exhausts retries and raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_async_job_raises_after_max_retries():
    async def always_fails() -> None:
        raise ValueError("permanent error")

    with pytest.raises(ValueError, match="permanent error"):
        await retry_async_job(
            always_fails,
            max_retries=2,
            initial_delay_sec=0.0,
        )


# ---------------------------------------------------------------------------
# 6. Module event publishers dispatch to real EventBus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluation_events_publish_to_bus():
    from app.modules.evaluation.events import EvaluationCompleted, publish_evaluation_completed

    collector = _Collector()
    event_bus.subscribe(EVALUATION_COMPLETED, collector)

    evt = EvaluationCompleted(
        evaluation_public_id="eval-abc",
        attempt_id=10,
        total_marks=80.0,
        percentage=80.0,
        result_status="PASS",
    )
    await publish_evaluation_completed(evt)

    matching = [c for c in collector.calls if c.get("evaluation_public_id") == "eval-abc"]
    assert len(matching) >= 1
    assert matching[-1]["attempt_id"] == 10
    assert matching[-1]["result_status"] == "PASS"


@pytest.mark.asyncio
async def test_analytics_events_publish_to_bus():
    from app.modules.analytics.events import AnalyticsUpdated, publish_analytics_updated

    collector = _Collector()
    event_bus.subscribe(ANALYTICS_UPDATED, collector)

    evt = AnalyticsUpdated(student_id=5, class_id=None, is_at_risk=True)
    await publish_analytics_updated(evt)

    matching = [c for c in collector.calls if c.get("student_id") == 5]
    assert matching[-1]["is_at_risk"] is True


@pytest.mark.asyncio
async def test_reports_events_publish_to_bus():
    from app.modules.reports.events import ReportGenerated, publish_report_generated

    collector = _Collector()
    event_bus.subscribe(REPORT_GENERATED, collector)

    evt = ReportGenerated(
        report_public_id="rpt-xyz",
        report_type="STUDENT_REPORT_CARD",
        student_id=7,
        exam_id=None,
    )
    await publish_report_generated(evt)

    matching = [c for c in collector.calls if c.get("report_public_id") == "rpt-xyz"]
    assert len(matching) >= 1


@pytest.mark.asyncio
async def test_exam_management_events_publish_to_bus():
    from app.modules.exam_management.events import ExamSubmitted, publish_exam_submitted

    collector = _Collector()
    event_bus.subscribe(EXAM_SUBMITTED, collector)

    evt = ExamSubmitted(
        attempt_public_id="att-001",
        exam_id=3,
        student_id=11,
        paper_id=22,
        submitted_at="2026-01-01T10:00:00Z",
    )
    await publish_exam_submitted(evt)

    matching = [c for c in collector.calls if c.get("attempt_public_id") == "att-001"]
    assert len(matching) >= 1


@pytest.mark.asyncio
async def test_paper_generation_events_publish_to_bus():
    from app.modules.paper_generation.events import PaperGenerated, publish_paper_generated

    collector = _Collector()
    event_bus.subscribe(PAPER_GENERATED, collector)

    evt = PaperGenerated(
        paper_public_id="ppr-999",
        exam_configuration_id=88,
        student_id=None,
        status="GENERATED",
        total_marks=100.0,
    )
    await publish_paper_generated(evt)

    matching = [c for c in collector.calls if c.get("paper_public_id") == "ppr-999"]
    assert len(matching) >= 1


@pytest.mark.asyncio
async def test_question_bank_events_publish_to_bus():
    from app.modules.question_bank.events import publish_question_imported

    collector = _Collector()
    event_bus.subscribe(QUESTION_IMPORTED, collector)

    await publish_question_imported("q-public-001", actor_id=5)

    matching = [c for c in collector.calls if c.get("question_public_id") == "q-public-001"]
    assert len(matching) >= 1
    assert matching[-1]["actor_id"] == 5


# ---------------------------------------------------------------------------
# 7. register_all_handlers wires expected number of subscribers
# ---------------------------------------------------------------------------

def test_register_all_handlers_populates_bus():
    """Calling register_all_handlers should wire ≥1 handler for each key event."""
    fresh_bus = EventBus()

    # Monkey-patch to use fresh bus for this test scope
    import app.core.events.handlers as _mod
    original_bus = _mod.event_bus

    # We test by checking subscribe is callable and by inspecting subscriber counts
    from app.core.events.handlers import register_all_handlers

    # register on the shared singleton (already called in some test runs - idempotent)
    # Just confirm the function runs without error
    register_all_handlers()

    # Check at least 1 handler exists on the shared bus for each event
    for event_name in [
        EXAM_SUBMITTED,
        EVALUATION_COMPLETED,
        MASTERY_UPDATED,
        LEARNING_PROFILE_UPDATED,
        ANALYTICS_UPDATED,
        REPORT_GENERATED,
    ]:
        assert len(event_bus._subscribers.get(event_name, [])) >= 1, (
            f"No handler registered for {event_name}"
        )
