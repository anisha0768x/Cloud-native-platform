import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.db import Database
from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1 import notification_router
from app.core.config import NotificationServiceSettings
from app.core.dependencies import build_channels
from app.services.dispatcher import NotificationDispatcher
from app.workers.escalation_worker import run_escalation_worker

settings = NotificationServiceSettings()
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

    worker_task: asyncio.Task | None = None
    if settings.ENABLE_ESCALATION_WORKER:
        channels = build_channels(settings, app.state.http_client)
        dispatcher = NotificationDispatcher(channels)
        worker_task = asyncio.create_task(
            run_escalation_worker(
                dispatcher=dispatcher,
                db=app.state.db,
                window_minutes=settings.ESCALATION_WINDOW_MINUTES,
                poll_seconds=settings.ESCALATION_WORKER_POLL_SECONDS,
            )
        )
    app.state.worker_task = worker_task

    logger.info("notification-service starting up")
    yield

    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await app.state.http_client.aclose()
    await app.state.db.dispose()
    logger.info("notification-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Notification Service",
        description="Routes alerts to webhook/Slack/email channels with unacknowledged-alert escalation.",
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
    app.include_router(notification_router)

    async def db_check() -> bool:
        return await app.state.db.health_check()

    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"database": db_check})
    )

    return app


app = create_app()
