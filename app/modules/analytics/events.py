"""
Analytics Engine module — Domain Events (Phase 16 §11 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import ANALYTICS_UPDATED


@dataclass(frozen=True)
class AnalyticsUpdated:
    student_id: int | None
    class_id: int | None
    is_at_risk: bool


async def publish_analytics_updated(event: AnalyticsUpdated) -> None:
    await event_bus.publish(ANALYTICS_UPDATED, asdict(event))
