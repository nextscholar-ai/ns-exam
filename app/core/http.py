"""
Shared HTTP client factory for Exam Engine (Phase 4).

Provides a singleton httpx.AsyncClient with connection pooling for all
outbound HTTP calls (ERP sync, webhook delivery, ERP auth validation).

Phase 4 replaces per-request httpx.AsyncClient creation with a shared
client to improve performance under load and prevent connection exhaustion.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Singleton HTTP client instance
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client singleton.

    Uses connection pooling with:
    - max_connections=20 (total concurrent connections)
    - max_keepalive_connections=10 (keepalive connections)
    - keepalive_expiry=30s (close idle connections after 30s)
    """
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,
                read=10.0,
                write=5.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30,
            ),
            headers={
                "User-Agent": f"exam-engine/{settings.app_version}",
                "Accept": "application/json",
            },
        )
        logger.info(
            "http.client.created",
            max_connections=20,
            max_keepalive=10,
            keepalive_expiry=30,
        )
    return _http_client


async def close_http_client() -> None:
    """Dispose the shared HTTP client on application shutdown."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
        logger.info("http.client.closed")


@asynccontextmanager
async def get_http_client_ctx() -> AsyncIterator[httpx.AsyncClient]:
    """Context manager that yields the shared HTTP client.

    Usage:
        async with get_http_client_ctx() as client:
            response = await client.get(url)
    """
    client = get_http_client()
    try:
        yield client
    finally:
        pass  # Client is shared, don't close on each use
