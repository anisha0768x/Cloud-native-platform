from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1 import dashboard_router
from app.core.config import DashboardServiceSettings

settings = DashboardServiceSettings()
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
    app.state.http_client = httpx.AsyncClient()
    app.state.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    logger.info("dashboard-service starting up")
    yield

    await app.state.http_client.aclose()
    await app.state.redis.aclose()
    logger.info("dashboard-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dashboard Service",
        description="BFF aggregation layer: combines Monitoring/Metrics/K8s Management data per dashboard, Redis-cached.",
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
    app.include_router(dashboard_router)

    async def redis_check() -> bool:
        try:
            await app.state.redis.ping()
            return True
        except Exception:
            return False

    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"redis": redis_check})
    )

    return app


app = create_app()
