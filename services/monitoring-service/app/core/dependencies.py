from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MonitoringServiceSettings
from app.repositories.alert_repository import AlertRepository
from app.repositories.service_repository import ServiceRepository
from app.services.monitoring_service import MonitoringService


def get_settings(request: Request) -> MonitoringServiceSettings:
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


def get_monitoring_service(
    session: AsyncSession = Depends(get_db_session),
    settings: MonitoringServiceSettings = Depends(get_settings),
) -> MonitoringService:
    return MonitoringService(
        service_repo=ServiceRepository(session),
        alert_repo=AlertRepository(session),
        consecutive_failures_before_down=settings.CONSECUTIVE_FAILURES_BEFORE_DOWN,
        health_summary_window_size=settings.HEALTH_SUMMARY_WINDOW_SIZE,
    )

