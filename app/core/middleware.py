"""
Cross-cutting HTTP middleware (Phase 7 §4-5.8).

Pipeline: [Rate Limit] -> [Request Context / Request-ID] -> [Response Envelope]
-> router -> service -> repository -> DB, then back out through the global
exception handler for any raised `DomainError`.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import DomainError, RateLimitedError
from app.core.logging import get_logger
from app.core.rate_limit import RateLimiter
from app.shared.constants import REQUEST_ID_HEADER

logger = get_logger(__name__)

ENVELOPE_PREFIX = "/api/v1"


def _meta(request_id: str, extra: dict | None = None) -> dict:
    meta = {"request_id": request_id, "timestamp": datetime.now(timezone.utc).isoformat()}
    if extra:
        meta.update(extra)
    return meta


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a request-id and binds it into structlog's
    contextvars so every log line inside the request carries it automatically
    (Phase 7 §11)."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    """
    Wraps every successful `/api/v1/*` JSON response in the standard envelope
    (Phase 7 §5.2):
        {"success": true, "data": ..., "meta": {"request_id": ..., "timestamp": ...}}

    A `Page[...]`-shaped body (has `items`/`total`/`page`/`page_size` keys) is
    unwrapped specially: `data` becomes the item list, and `page`/`page_size`/
    `total`/`total_pages` move into `meta`, matching the documented paginated
    shape exactly. Error responses are already enveloped by the global
    exception handler and are left untouched.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if not request.url.path.startswith(ENVELOPE_PREFIX):
            return response
        if response.status_code >= 400:
            return response  # already enveloped by the exception handler
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk

        try:
            original = json.loads(body) if body else None
        except json.JSONDecodeError:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

        if (
            isinstance(original, dict)
            and {"items", "total", "page", "page_size"} <= original.keys()
        ):
            page_size = original["page_size"] or 1
            total_pages = max(1, (original["total"] + page_size - 1) // page_size)
            envelope = {
                "success": True,
                "data": original["items"],
                "meta": _meta(
                    request_id,
                    {
                        "page": original["page"],
                        "page_size": original["page_size"],
                        "total": original["total"],
                        "total_pages": total_pages,
                    },
                ),
            }
        else:
            envelope = {"success": True, "data": original, "meta": _meta(request_id)}

        new_body = json.dumps(envelope).encode("utf-8")
        headers = dict(response.headers)
        headers["content-length"] = str(len(new_body))
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket rate limiting (Phase 7 §5.8): keyed by `user_id` when
    authenticated, else by client IP - stricter limits on `/auth/*`.

    v1 limitation (documented, not hidden): the bucket lives in per-process
    memory, which is correct for a single app instance and becomes an
    approximation once horizontally scaled - swap `RateLimiter` for a
    Redis-backed implementation at that point without changing this
    middleware's interface.
    """

    def __init__(self, app, limiter: RateLimiter) -> None:
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        key = self._bucket_key(request)
        is_auth_path = request.url.path.startswith(f"{ENVELOPE_PREFIX}/identity/auth")

        allowed = self.limiter.allow(key, strict=is_auth_path)
        if not allowed:
            exc = RateLimitedError("Too many requests - please slow down")
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "error": {
                        "code": exc.error_code,
                        "message": exc.message,
                        "details": {},
                    },
                    "meta": _meta(getattr(request.state, "request_id", str(uuid.uuid4()))),
                },
            )
        return await call_next(request)

    @staticmethod
    def _bucket_key(request: Request) -> str:
        # Authenticated user_id isn't resolved yet at middleware time without
        # decoding the token twice; bucket by the raw Authorization header
        # value when present (still per-caller), else by client IP.
        auth_header = request.headers.get("authorization")
        if auth_header:
            return f"auth:{auth_header[-24:]}"  # last chars are enough entropy for bucketing
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic/FastAPI request-body validation errors, converted into the
        same envelope as domain errors (Phase 7 §5.5) - never FastAPI's raw
        default shape."""
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.warning("request_validation_error", errors=exc.errors(), path=request.url.path)
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                },
                "meta": _meta(request_id),
            },
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.warning(
            "domain_error",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "meta": _meta(request_id),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {},
                },
                "meta": _meta(request_id),
            },
        )
