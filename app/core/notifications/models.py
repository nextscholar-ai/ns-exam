"""
Notification System — ORM Models (Phase 19 §3).

Table owned here:
  notification_logs — audit log of all outbound notifications (email, push, webhook, log).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base_model import Base, BaseMixin


class NotificationLog(BaseMixin, Base):
    """
    Audit log of outgoing notification attempts (Phase 19 §3).

    Tracks channel, recipient identifier (user_id / email / device_token),
    notification_type, delivery status (SENT, FAILED, MOCKED), subject/title,
    message body preview, error trace, and delivery timestamp.
    """

    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_nl_channel", "channel"),
        Index("ix_nl_status", "status"),
        Index("ix_nl_notification_type", "notification_type"),
        Index("ix_nl_recipient_id", "recipient_id"),
    )

    channel: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # EMAIL | PUSH | WEBHOOK | LOG
    notification_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # REPORT_READY | STUDENT_AT_RISK | JOB_COMPLETED | TEST_NOTIFICATION ...
    recipient_id: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # user_id or email or token
    recipient_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="USER"
    )  # STUDENT | TEACHER | ADMIN | USER | SYSTEM
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING | SENT | FAILED | MOCKED
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
