from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.metrics_client import MetricsClient
from app.core.config import TrafficPredictionServiceSettings
from app.repositories.prediction_repository import PredictionRepository
from app.services.prediction_service import PredictionService


def get_settings(request: Request) -> TrafficPredictionServiceSettings:
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


def get_prediction_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> PredictionService:
    settings: TrafficPredictionServiceSettings = request.app.state.settings
    metrics_client = MetricsClient(
        request.app.state.http_client, settings.METRICS_SERVICE_URL, timeout=settings.BACKEND_CALL_TIMEOUT_SECONDS
    )
    return PredictionService(
        metrics_client,
        PredictionRepository(session),
        lookback_hours=settings.LOOKBACK_HOURS,
        min_training_points=settings.MIN_TRAINING_POINTS,
        requests_per_pod_capacity=settings.REQUESTS_PER_POD_CAPACITY,
        model_cache_ttl_seconds=settings.MODEL_CACHE_TTL_SECONDS,
    )
