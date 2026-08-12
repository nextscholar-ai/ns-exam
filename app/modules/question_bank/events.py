"""
Question Bank module — Domain Events (Phase 17 §3).

Real async event publishers dispatching through `app.core.events.bus.event_bus`.
"""
from __future__ import annotations

from app.core.events.bus import event_bus
from app.core.events.event_names import (
    QUESTION_IMPORTED,
    QUESTION_VERSION_CREATED,
)


async def publish_question_imported(
    question_public_id: str,
    actor_id: int | None = None,
) -> None:
    await event_bus.publish(
        QUESTION_IMPORTED,
        {"question_public_id": question_public_id, "actor_id": actor_id},
    )


async def publish_question_version_created(
    question_public_id: str,
    version_no: int,
    actor_id: int | None = None,
) -> None:
    await event_bus.publish(
        QUESTION_VERSION_CREATED,
        {
            "question_public_id": question_public_id,
            "version_no": version_no,
            "actor_id": actor_id,
        },
    )
