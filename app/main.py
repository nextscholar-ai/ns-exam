"""
FastAPI application factory.

Phase 5 exit criteria: this file must boot successfully with every module
router registered (even with zero real endpoints yet) before Phase 6
(Authentication) implementation begins.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.db.session import check_db_connection, engine
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, register_exception_handlers

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", env=settings.app_env, version=settings.app_version)
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/db", tags=["health"])
    async def health_db() -> dict[str, str]:
        ok = await check_db_connection()
        return {"status": "ok" if ok else "unavailable"}

    return app


app = create_app()
