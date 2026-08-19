from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_common.exceptions import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging import configure_logging, get_logger

from app.api.v1 import storage_router
from app.core.config import CloudStorageServiceSettings
from app.storage.s3_provider import S3StorageProvider

settings = CloudStorageServiceSettings()
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
    app.state.storage_provider = S3StorageProvider(
        bucket=settings.S3_BUCKET,
        endpoint_url=settings.S3_ENDPOINT_URL,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        region=settings.S3_REGION,
    )
    await app.state.storage_provider.ensure_bucket_exists()

    logger.info("cloud-storage-service starting up", extra={"bucket": settings.S3_BUCKET})
    yield
    logger.info("cloud-storage-service shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cloud Storage Service",
        description="S3-compatible object storage for log archives, reports, and exports.",
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
    app.include_router(storage_router)

    async def storage_check() -> bool:
        try:
            await app.state.storage_provider.list_objects(limit=1)
            return True
        except Exception:
            return False

    app.include_router(
        build_health_router(settings.SERVICE_NAME, settings.SERVICE_VERSION, {"storage": storage_check})
    )

    return app


app = create_app()
