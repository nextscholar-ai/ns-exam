"""
FastAPI application factory.

Phase 5 exit criteria: boots with every module router registered.
Phase 7 adds the middleware pipeline (rate limiting, request-id, response
envelope) and the global `/api/v1/jobs/{job_id}` contract on top.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.db.session import check_db_connection, engine
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

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", env=settings.app_env, version=settings.app_version)
    register_identity_event_handlers()
    register_all_handlers()
    yield
    logger.info("app.shutdown")
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

    # Middleware pipeline (Phase 7 §4), outermost to innermost:
    # CORS -> RateLimit -> RequestContext -> ResponseEnvelope -> router.
    # add_middleware() makes the LAST call the OUTERMOST layer, so these are
    # added innermost-first.
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

    return app


app = create_app()
