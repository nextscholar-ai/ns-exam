"""
Identity module — event handlers (Phase 6 §17-18).

`UserRegistered` / `UserLoggedIn` / `UserLoggedOut` are published on the
in-process bus. `login_history` writes already happen synchronously inside
`IdentityService` (simpler, same transaction) - these handlers are for
secondary consumers (e.g. future analytics) that must NOT block the login
transaction itself.
"""
from __future__ import annotations

from typing import Any

from app.core.events.bus import event_bus
from app.core.logging import get_logger
from app.modules.identity.service import USER_LOGGED_IN, USER_LOGGED_OUT, USER_REGISTERED

logger = get_logger(__name__)


async def _on_user_registered(payload: dict[str, Any]) -> None:
    logger.info("identity.event.user_registered", **payload)


async def _on_user_logged_in(payload: dict[str, Any]) -> None:
    logger.info("identity.event.user_logged_in", **payload)


async def _on_user_logged_out(payload: dict[str, Any]) -> None:
    logger.info("identity.event.user_logged_out", **payload)


def register_identity_event_handlers() -> None:
    event_bus.subscribe(USER_REGISTERED, _on_user_registered)
    event_bus.subscribe(USER_LOGGED_IN, _on_user_logged_in)
    event_bus.subscribe(USER_LOGGED_OUT, _on_user_logged_out)
