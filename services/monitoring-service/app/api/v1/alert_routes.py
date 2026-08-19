import uuid

from fastapi import APIRouter, Depends, Query, status

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_monitoring_service
from app.schemas.monitoring import AlertResponse
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    service_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("alert:read")),
):
    return await monitoring.list_alerts(service_id=service_id, status=status_filter, severity=severity)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    token: TokenPayload = Depends(require_permission("alert:acknowledge")),
):
    return await monitoring.acknowledge_alert(alert_id, acknowledged_by=token.sub)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: uuid.UUID,
    monitoring: MonitoringService = Depends(get_monitoring_service),
    _: TokenPayload = Depends(require_permission("alert:acknowledge")),
):
    return await monitoring.resolve_alert(alert_id)
