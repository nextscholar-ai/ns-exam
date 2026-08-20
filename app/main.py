"""
FastAPI application factory.

Phase 5 exit criteria: boots with every module router registered.
Phase 7 adds the middleware pipeline (rate limiting, request-id, response
envelope) and the global `/api/v1/jobs/{job_id}` contract on top.
Phase 4 adds shared HTTP client lifecycle management.
"""
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.db.session import check_db_connection, engine
from app.core.http import close_http_client
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    ResponseEnvelopeMiddleware,
    register_exception_handlers,
)
from app.core.rate_limit import rate_limiter
from app.jobs.router import router as jobs_router
from app.modules.identity.events import register_identity_event_handlers
from app.core.events.handlers import register_all_handlers
from app.modules.integration.events import register_integration_event_handlers

from app.core.security.headers import SecurityHeadersMiddleware

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", env=settings.app_env, version=settings.app_version)
    register_identity_event_handlers()
    register_all_handlers()
    register_integration_event_handlers()
    yield
    logger.info("app.shutdown")
    await close_http_client()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Exam Engine",
        description="AI-Powered Intelligent Assessment Platform",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # Middleware pipeline (Phase 7 & Phase 21), outermost to innermost:
    # SecurityHeaders -> CORS -> RateLimit -> RequestContext -> ResponseEnvelope -> router.
    app.add_middleware(ResponseEnvelopeMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/db", tags=["health"])
    async def health_db() -> dict[str, str]:
        ok = await check_db_connection()
        return {"status": "ok" if ok else "unavailable"}

    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, str]:
        """Liveness probe: verifies process responsiveness."""
        return {"status": "ALIVE", "version": settings.app_version}

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, Any]:
        """Readiness probe: verifies DB connectivity and core component state."""
        db_ok = await check_db_connection()
        status = "READY" if db_ok else "NOT_READY"
        notif_enabled = settings.notification.email_enabled or settings.notification.push_enabled
        return {
            "status": status,
            "components": {
                "database": "CONNECTED" if db_ok else "DISCONNECTED",
                "notifications": "ENABLED" if notif_enabled else "DISABLED",
            },
        }

    @app.get("/health/metrics", tags=["health"])
    async def health_metrics() -> dict[str, Any]:
        """Production observability metrics summary."""
        db_ok = await check_db_connection()
        return {
            "app_env": settings.app_env,
            "app_version": settings.app_version,
            "database_connected": db_ok,
            "rate_limiter": "active",
        }

    return app


app = create_app()
