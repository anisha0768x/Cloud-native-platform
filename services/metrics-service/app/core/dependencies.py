from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MetricsServiceSettings
from app.repositories.metric_repository import MetricRepository
from app.services.metrics_service import MetricsService


def get_settings(request: Request) -> MetricsServiceSettings:
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


def get_metrics_service(
    session: AsyncSession = Depends(get_db_session),
    settings: MetricsServiceSettings = Depends(get_settings),
) -> MetricsService:
    return MetricsService(MetricRepository(session), max_query_range_days=settings.MAX_QUERY_RANGE_DAYS)
