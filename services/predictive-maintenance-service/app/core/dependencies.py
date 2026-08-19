from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.k8s_client import K8sClient
from app.clients.metrics_client import MetricsClient
from app.core.config import PredictiveMaintenanceServiceSettings
from app.repositories.maintenance_repository import MaintenancePredictionRepository
from app.services.maintenance_service import MaintenanceService


def get_settings(request: Request) -> PredictiveMaintenanceServiceSettings:
    return request.app.state.settings


async def get_db_session(request: Request) -> AsyncSession:
    async with request.app.state.db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_maintenance_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> MaintenanceService:
    settings: PredictiveMaintenanceServiceSettings = request.app.state.settings
    metrics_client = MetricsClient(
        request.app.state.http_client, settings.METRICS_SERVICE_URL, timeout=settings.BACKEND_CALL_TIMEOUT_SECONDS
    )
    k8s_client = K8sClient(
        request.app.state.http_client, settings.K8S_MANAGEMENT_SERVICE_URL, timeout=settings.BACKEND_CALL_TIMEOUT_SECONDS
    )
    return MaintenanceService(
        metrics_client,
        k8s_client,
        MaintenancePredictionRepository(session),
        feature_lookback_hours=settings.FEATURE_LOOKBACK_HOURS,
        training_sample_count=settings.TRAINING_SAMPLE_COUNT,
        model_cache_ttl_seconds=settings.MODEL_CACHE_TTL_SECONDS,
    )
