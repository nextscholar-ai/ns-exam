"""
Mastery Engine module — Domain Events (Phase 14 §11 / Phase 17 §3).

Real event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.core.events.bus import event_bus
from app.core.events.event_names import MASTERY_UPDATED


@dataclass(frozen=True)
class MasteryUpdated:
    student_id: int
    evaluation_public_id: str
    topics_updated: int
    chapters_updated: int
    subjects_updated: int
    weak_topic_ids: list[int]


async def publish_mastery_updated(event: MasteryUpdated) -> None:
    await event_bus.publish(MASTERY_UPDATED, asdict(event))
