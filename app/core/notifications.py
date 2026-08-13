"""
Core Notification Module Forwarder (Phase 19 §3).

Re-exports `NotificationDispatcher` and `notification_dispatcher` from
`app.core.notifications.service` for backward compatibility.
"""
from __future__ import annotations

from app.core.notifications.service import (
    NotificationDispatcher,
    notification_dispatcher,
)

__all__ = ["NotificationDispatcher", "notification_dispatcher"]
