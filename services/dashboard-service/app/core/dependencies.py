from fastapi import Depends, Request

from app.clients.backend_client import BackendClient
from app.core.config import DashboardServiceSettings
from app.services.dashboard_service import DashboardService


def get_settings(request: Request) -> DashboardServiceSettings:
    return request.app.state.settings


def get_dashboard_service(request: Request) -> DashboardService:
    settings: DashboardServiceSettings = request.app.state.settings
    http_client = request.app.state.http_client

    monitoring = BackendClient(
        http_client, settings.MONITORING_SERVICE_URL, timeout=settings.BACKEND_CALL_TIMEOUT_SECONDS
    )
    k8s = BackendClient(
        http_client, settings.K8S_MANAGEMENT_SERVICE_URL, timeout=settings.BACKEND_CALL_TIMEOUT_SECONDS
    )

    return DashboardService(
        monitoring, k8s, request.app.state.redis, cache_ttl_seconds=settings.CACHE_TTL_SECONDS
    )
