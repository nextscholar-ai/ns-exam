"""
Centralized structured logging module.

Every log line is emitted with structured context, timestamp (UTC), log level,
logger name, and request_id + user_id bound by contextvars/middleware.

Supports:
  - Console colored logging for development CLI.
  - Rotating JSON log file output (logs/app.log).
  - Integration with structlog and standard logging.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False
    structlog = None  # type: ignore

from app.core.config import settings


# Context variables for tracing across async execution flows
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="-")


class JSONFormatter(logging.Formatter):
    """Formatter that outputs JSON strings for logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineNo": record.lineno,
            "request_id": request_id_ctx.get(),
            "user_id": user_id_ctx.get(),
        }
        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


class ColorFormatter(logging.Formatter):
    """Console formatter with colors for local development."""

    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[41;97;1m"
    RESET = "\x1b[0m"

    LEVEL_COLORS = {
        logging.DEBUG: GREY,
        logging.INFO: BLUE,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        usr_id = user_id_ctx.get()
        ctx = f"[req:{req_id} usr:{usr_id}]" if req_id != "-" else ""

        base_format = f"%(asctime)s [%(levelname)s] {ctx} %(name)s.%(funcName)s:%(lineno)d - %(message)s"
        base = logging.Formatter(base_format, datefmt="%Y-%m-%d %H:%M:%S").format(record)

        if not sys.stdout.isatty():
            return base

        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        return f"{color}{base}{self.RESET}"


def configure_logging(log_dir: str = "logs") -> None:
    """Call once at application startup (see main.py)."""
    log_level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    console_level_name = getattr(settings.logging, "console_level", "WARNING").upper()
    console_level = getattr(logging, console_level_name, logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = getattr(settings.logging, "file_path", os.path.join(log_dir, "app.log"))
    except Exception:
        log_file_path = os.path.join(log_dir, "app.log")

    if HAS_STRUCTLOG:
        shared_processors: list = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # 1. File Handler (writes structured JSON lines to logs/app.log)
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processor=structlog.processors.JSONRenderer(),
                    foreign_pre_chain=shared_processors,
                )
            )
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        except Exception:
            pass

        # 2. Console Handler (clean human-readable formatting, defaults to WARNING so terminal is not flooded)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
                foreign_pre_chain=shared_processors,
            )
        )
        console_handler.setLevel(console_level)
        root_logger.addHandler(console_handler)

    else:
        # Fallback when structlog is not present
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(JSONFormatter())
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        except Exception:
            pass

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColorFormatter())
        console_handler.setLevel(console_level)
        root_logger.addHandler(console_handler)


class BoundLoggerAdapter:
    """Wrapper around logging.Logger that converts keyword arguments into formatted string or extra dict."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _format_msg(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.pop("extra", {})
        if kwargs:
            kv_str = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
            msg = f"{msg} {kv_str}"
        return msg, extra

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        msg, extra = self._format_msg(msg, kwargs)
        self._logger.info(msg, *args, extra=extra)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        msg, extra = self._format_msg(msg, kwargs)
        self._logger.debug(msg, *args, extra=extra)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        msg, extra = self._format_msg(msg, kwargs)
        self._logger.warning(msg, *args, extra=extra)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        msg, extra = self._format_msg(msg, kwargs)
        self._logger.error(msg, *args, extra=extra)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        msg, extra = self._format_msg(msg, kwargs)
        self._logger.exception(msg, *args, extra=extra)


def get_logger(name: str = "exam_engine") -> Any:
    """
    Usage:
        logger = get_logger(__name__)
        logger.info("question.created", question_id=q.public_id)
    """
    if HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return BoundLoggerAdapter(logging.getLogger(name))



