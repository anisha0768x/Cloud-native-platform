from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.gateway_routes import router as gateway_router
from app.core.config import GatewaySettings
from app.core.rate_limiter import RateLimiter

settings = GatewaySettings()
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

    # ONE shared httpx client for the process, not one per request — reuses
    # connection pools to every upstream instead of paying a new TCP+TLS
    # handshake on every single proxied call.
    app.state.http_client = httpx.AsyncClient(timeout=settings.UPSTREAM_TIMEOUT_SECONDS)

    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.redis = redis_client
    app.state.rate_limiter = RateLimiter(
        redis_client,
        max_requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    logger.info("api-gateway starting up", extra={"routes": [r.prefix for r in settings.route_table]})
    yield

    await app.state.http_client.aclose()
    await redis_client.aclose()
    logger.info("api-gateway shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="API Gateway",
        description="Single entry point: routing, coarse auth, rate limiting for all platform services.",
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

    async def redis_check() -> bool:
        try:
            await app.state.redis.ping()
            return True
        except Exception:
            return False

    # Registered BEFORE the catch-all router: Starlette matches routes in
    # registration order, so these literal /health and /ready paths must
    # win against the `/{full_path:path}` catch-all, not be swallowed by it.
    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"redis": redis_check})
    )
    app.include_router(gateway_router)

    return app


app = create_app()
