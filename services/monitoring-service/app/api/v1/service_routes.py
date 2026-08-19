import uuid

from fastapi import APIRouter, Depends, Query, status

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_monitoring_service
from app.schemas.monitoring import (
    HealthSummaryResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    ServiceCreateRequest,
    ServiceResponse,
)
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/api/v1/services", tags=["services"])


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def register_service(
    body: ServiceCreateRequest,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("service:create")),
):
    service = await monitoring.register_service(
        name=body.name, type=body.type, namespace=body.namespace, owner_team=body.owner_team
    )
    return service


@router.get("", response_model=list[ServiceResponse])
async def list_services(
    status_filter: str | None = Query(default=None, alias="status"),
    namespace: str | None = Query(default=None),
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await monitoring.list_services(status=status_filter, namespace=namespace)


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: uuid.UUID,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await monitoring.get_service_or_404(service_id)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: uuid.UUID,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("service:delete")),
):
    await monitoring.delete_service(service_id)


@router.post("/{service_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    service_id: uuid.UUID,
    body: HeartbeatRequest,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("service:update")),
):
    return await monitoring.record_heartbeat(
        service_id, healthy=body.healthy, latency_ms=body.latency_ms, detail=body.detail
    )


@router.get("/{service_id}/health-summary", response_model=HealthSummaryResponse)
async def health_summary(
    service_id: uuid.UUID,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await monitoring.health_summary(service_id)
