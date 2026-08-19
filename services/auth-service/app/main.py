"""
Application entrypoint: wires together settings, DB, logging, exception
handlers, and routers. This is the only file that should ever import from
platform_common's setup functions directly — every other file gets its
dependencies injected, keeping main.py the single "composition root".
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.db import Database
from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1 import auth_router
from app.core.config import AuthServiceSettings

settings = AuthServiceSettings()
configure_logging(
    service_name=settings.SERVICE_NAME,
    service_version=settings.SERVICE_VERSION,
    environment=settings.ENVIRONMENT,
    log_level=settings.LOG_LEVEL,
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.db = Database(settings.DATABASE_URL, echo=settings.is_local)
    logger.info("auth-service starting up", extra={"environment": settings.ENVIRONMENT})
    yield
    await app.state.db.dispose()
    logger.info("auth-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Auth Service",
        description="Authentication, authorization (RBAC), and identity for the platform.",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(auth_router)

    async def db_check() -> bool:
        return await app.state.db.health_check()

    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"database": db_check})
    )

    return app


app = create_app()
