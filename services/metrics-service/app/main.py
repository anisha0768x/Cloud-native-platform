import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.db import Database
from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1.metric_routes import router as metrics_router
from app.core.config import MetricsServiceSettings
from app.workers.metrics_consumer import run_metrics_consumer

settings = MetricsServiceSettings()
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

    consumer_task: asyncio.Task | None = None
    if settings.ENABLE_KAFKA_CONSUMER:
        consumer_task = asyncio.create_task(
            run_metrics_consumer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                topic=settings.METRICS_TOPIC,
                group_id=settings.KAFKA_CONSUMER_GROUP,
                db=app.state.db,
                max_query_range_days=settings.MAX_QUERY_RANGE_DAYS,
            )
        )
    app.state.consumer_task = consumer_task

    logger.info("metrics-service starting up", extra={"kafka_consumer_enabled": settings.ENABLE_KAFKA_CONSUMER})
    yield

    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    await app.state.db.dispose()
    logger.info("metrics-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Metrics Service",
        description="Time-series metrics ingestion (Kafka + REST fallback) and aggregation queries.",
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
    app.include_router(metrics_router)

    async def db_check() -> bool:
        return await app.state.db.health_check()

    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"database": db_check})
    )

    return app


app = create_app()
