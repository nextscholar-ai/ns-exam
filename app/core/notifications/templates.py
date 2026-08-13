"""
Notification System — Template Registry & Renderer (Phase 19 §3).

Renders subject line, plain text body, and HTML body for notification types.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderedTemplate:
    subject: str
    text_body: str
    html_body: str


class NotificationTemplateRegistry:
    """Renders formatted messages for supported notification events."""

    @staticmethod
    def render(notification_type: str, context: dict[str, Any]) -> RenderedTemplate:
        handler = getattr(
            NotificationTemplateRegistry,
            f"_render_{notification_type.lower()}",
            NotificationTemplateRegistry._render_default,
        )
        return handler(context)

    @staticmethod
    def _render_report_ready(context: dict[str, Any]) -> RenderedTemplate:
        student_id = context.get("student_id", "N/A")
        report_public_id = context.get("report_public_id", "")
        report_type = context.get("report_type", "Report Card")

        subject = f"Your {report_type} is Ready"
        text_body = (
            f"Hello Student #{student_id},\n\n"
            f"Your {report_type} (ID: {report_public_id}) is now available for view and download.\n"
            "Log in to your dashboard to inspect your full performance summary."
        )
        html_body = (
            f"<h2>Your {report_type} is Ready</h2>"
            f"<p>Hello Student #{student_id},</p>"
            f"<p>Your report card (ID: <code>{report_public_id}</code>) has been generated successfully.</p>"
            "<p><a href='/reports'>Click here to view your report</a></p>"
        )
        return RenderedTemplate(subject=subject, text_body=text_body, html_body=html_body)

    @staticmethod
    def _render_student_at_risk(context: dict[str, Any]) -> RenderedTemplate:
        student_id = context.get("student_id", "N/A")

        subject = f"Academic Risk Alert for Student #{student_id}"
        text_body = (
            f"Attention Teacher/Admin,\n\n"
            f"Student #{student_id} has been flagged as at-risk based on recent mastery and score analytics.\n"
            "Please review their learning profile to assign targeted recommendations."
        )
        html_body = (
            f"<h2>Academic Risk Alert</h2>"
            f"<p>Student <strong>#{student_id}</strong> is currently flagged as <code>AT_RISK</code>.</p>"
            "<p>Please review their weak topics and assign practice recommendations.</p>"
        )
        return RenderedTemplate(subject=subject, text_body=text_body, html_body=html_body)

    @staticmethod
    def _render_job_completed(context: dict[str, Any]) -> RenderedTemplate:
        job_id = context.get("job_id", "")
        job_type = context.get("job_type", "Background Task")

        subject = f"Background Task Completed: {job_type}"
        text_body = f"Task '{job_type}' (Job ID: {job_id}) completed execution successfully."
        html_body = f"<p>Task <strong>{job_type}</strong> (<code>{job_id}</code>) has completed.</p>"
        return RenderedTemplate(subject=subject, text_body=text_body, html_body=html_body)

    @staticmethod
    def _render_exam_published(context: dict[str, Any]) -> RenderedTemplate:
        exam_id = context.get("exam_public_id", "")
        join_code = context.get("join_code", "")

        subject = "New Exam Published"
        text_body = f"An exam (ID: {exam_id}) has been published. Join code: {join_code}"
        html_body = f"<p>Exam <code>{exam_id}</code> published. Code: <strong>{join_code}</strong></p>"
        return RenderedTemplate(subject=subject, text_body=text_body, html_body=html_body)

    @staticmethod
    def _render_test_notification(context: dict[str, Any]) -> RenderedTemplate:
        message = context.get("message", "Test notification message")
        subject = "Exam Engine Test Notification"
        text_body = f"Test Notification: {message}"
        html_body = f"<h3>Test Notification</h3><p>{message}</p>"
        return RenderedTemplate(subject=subject, text_body=text_body, html_body=html_body)

    @staticmethod
    def _render_default(context: dict[str, Any]) -> RenderedTemplate:
        msg = context.get("message", "System notification")
        subject = "System Notification"
        text_body = str(msg)
        html_body = f"<p>{msg}</p>"
        return RenderedTemplate(subject=subject, text_body=text_body, html_body=html_body)
