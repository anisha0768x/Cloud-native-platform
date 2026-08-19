import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.db import Database
from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1 import k8s_router
from app.core.config import K8sManagementServiceSettings
from app.providers import build_cluster_provider
from app.workers.snapshot_worker import run_snapshot_worker

settings = K8sManagementServiceSettings()
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
    app.state.cluster_provider = build_cluster_provider(settings.CLUSTER_MODE)

    worker_task: asyncio.Task | None = None
    if settings.ENABLE_SNAPSHOT_WORKER:
        worker_task = asyncio.create_task(
            run_snapshot_worker(
                provider=app.state.cluster_provider,
                db=app.state.db,
                interval_seconds=settings.SNAPSHOT_INTERVAL_SECONDS,
            )
        )
    app.state.worker_task = worker_task

    logger.info("k8s-management-service starting up", extra={"cluster_mode": settings.CLUSTER_MODE})
    yield

    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await app.state.db.dispose()
    logger.info("k8s-management-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kubernetes Management Service",
        description="Cluster state (nodes/pods/deployments) and scaling actions, via a pluggable cluster provider.",
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
    app.include_router(k8s_router)

    async def db_check() -> bool:
        return await app.state.db.health_check()

    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"database": db_check})
    )

    return app


app = create_app()
