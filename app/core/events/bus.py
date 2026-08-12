"""
In-process pub-sub event bus (Phase 2 §10).

v1 is a modular monolith: no Kafka/RabbitMQ. Event names + payload shape are
designed now so a future extraction to a real broker is a transport swap, not
a redesign. Each handler only depends on the event payload - never reaches
into another module's internals.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        self._subscribers[event_name].append(handler)
        logger.info("event_bus.subscribed", event_name=event_name, handler=handler.__qualname__)

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        logger.info("event_bus.published", event_name=event_name, payload_keys=list(payload.keys()))
        for handler in self._subscribers.get(event_name, []):
            try:
                await handler(payload)
            except Exception:
                # A failing handler must never break the publisher's transaction;
                # log and continue. Retry/dead-letter strategy is a Phase 17 concern.
                logger.exception(
                    "event_bus.handler_failed",
                    event_name=event_name,
                    handler=handler.__qualname__,
                )


event_bus = EventBus()
