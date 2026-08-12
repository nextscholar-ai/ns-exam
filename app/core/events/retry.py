"""
Core Events — Retry Policy & Exponential Backoff (Phase 17 §4).

Provides `retry_async_job` decorator and wrapper for background tasks
and event bus handlers.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def retry_async_job(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    initial_delay_sec: float = 0.5,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> T:
    """
    Execute an async function with exponential backoff retry.

    Args:
        func: Async function to execute.
        max_retries: Maximum attempt count (default 3).
        initial_delay_sec: Initial delay in seconds before first retry.
        backoff_factor: Multiplier applied to delay after each failure.
    """
    delay = initial_delay_sec
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exception = exc
            if attempt == max_retries:
                logger.error(
                    "retry_async_job.max_retries_exceeded",
                    func=func.__name__ if hasattr(func, "__name__") else str(func),
                    attempts=attempt,
                    error=str(exc),
                )
                raise exc

            logger.warning(
                "retry_async_job.attempt_failed",
                func=func.__name__ if hasattr(func, "__name__") else str(func),
                attempt=attempt,
                next_delay_sec=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
            delay *= backoff_factor

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry wrapper failed without exception")
