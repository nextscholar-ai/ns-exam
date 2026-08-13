"""
Core Notifications Package (Phase 19 §3).
"""
from __future__ import annotations

from app.core.notifications.service import (
    NotificationDispatcher,
    notification_dispatcher,
)

__all__ = ["NotificationDispatcher", "notification_dispatcher"]
