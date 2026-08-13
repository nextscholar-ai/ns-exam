"""
Notification System — Schemas (Phase 19 §3).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NotificationLogResponse(BaseModel):
    id: str
    channel: str
    notification_type: str
    recipient_id: str
    recipient_type: str
    status: str
    subject: str
    body_preview: str | None = None
    error_message: str | None = None
    sent_at: str | None = None
    created_at: str


class NotificationTestRequest(BaseModel):
    recipient_id: str = Field(..., description="Email, user ID, or device token")
    notification_type: str = Field("TEST_NOTIFICATION", description="Template key")
    channel: str = Field("EMAIL", description="EMAIL, PUSH, or MOCK")
    context: dict[str, Any] = Field(default_factory=dict, description="Template context variables")


class NotificationTestResponse(BaseModel):
    notification_type: str
    recipient_id: str
    channel: str
    status: str
    subject: str
    error: str | None = None
