import asyncio
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.db import Database
from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1 import genai_router, log_router
from app.core.config import GenAiLogAnalysisServiceSettings
from app.logstore import build_log_store
from app.workers.logs_consumer import run_logs_consumer

settings = GenAiLogAnalysisServiceSettings()
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
    app.state.http_client = httpx.AsyncClient()
    app.state.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.log_store = build_log_store(settings.LOG_STORE_MODE, settings.OPENSEARCH_HOSTS)

    consumer_task: asyncio.Task | None = None
    if settings.ENABLE_KAFKA_CONSUMER:
        consumer_task = asyncio.create_task(
            run_logs_consumer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                topic=settings.LOGS_TOPIC,
                group_id=settings.KAFKA_CONSUMER_GROUP,
                log_store=app.state.log_store,
            )
        )
    app.state.consumer_task = consumer_task

    logger.info(
        "genai-log-analysis-service starting up",
        extra={"log_store_mode": settings.LOG_STORE_MODE, "llm_configured": bool(settings.ANTHROPIC_API_KEY)},
    )
    yield

    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    await app.state.http_client.aclose()
    await app.state.redis.aclose()
    await app.state.db.dispose()
    logger.info("genai-log-analysis-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="GenAI Log Analysis Service",
        description="RAG-based log/incident analysis via Claude, with a rule-based fallback when the LLM is unavailable.",
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
    app.include_router(log_router)
    app.include_router(genai_router)

    async def db_check() -> bool:
        return await app.state.db.health_check()

    async def redis_check() -> bool:
        try:
            await app.state.redis.ping()
            return True
        except Exception:
            return False

    app.include_router(
        build_health_router(
            settings.SERVICE_NAME, settings.SERVICE_VERSION, {"database": db_check, "redis": redis_check}
        )
    )

    return app


app = create_app()
