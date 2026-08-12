"""
Centralized structured logging.

Every log line is emitted as structured JSON (production) or a readable console
format (development), always including: timestamp (UTC), log level, logger name,
and — whenever available — request_id + actor_user_id bound by the request
middleware (see `middleware.py`). Full audit-log persistence (DB-backed) is a
separate concern owned by Phase 18; this module is the cross-cutting logger used
by every layer (routers, services, repositories, jobs) starting from Phase 1.
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    """Call once, at application startup (see `main.py`)."""
    log_level = getattr(logging, settings.logging.level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.logging.format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Usage:
        logger = get_logger(__name__)
        logger.info("question.created", question_id=q.public_id, actor_id=user.id)

    Always log structured key=value context, never pre-formatted sentences with
    interpolated secrets/PII.
    """
    return structlog.get_logger(name)
