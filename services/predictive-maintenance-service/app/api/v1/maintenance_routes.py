import uuid

from fastapi import APIRouter, Depends, Header, Query

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_maintenance_service
from app.schemas.maintenance import MaintenanceHistoryEntry, MaintenancePredictionResponse
from app.services.maintenance_service import MaintenanceService

router = APIRouter(prefix="/api/v1/predictions/maintenance", tags=["predictive-maintenance"])


@router.get("/{service_id}", response_model=MaintenancePredictionResponse)
async def predict_failure_risk(
    service_id: uuid.UUID,
    service_name: str = Query(..., description="Used to match K8s pods for restart-count lookup"),
    authorization: str = Header(...),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
    _: TokenPayload = Depends(require_permission("metrics:read")),
):
    return await maintenance.predict(service_id=service_id, service_name=service_name, authorization=authorization)


@router.get("/{service_id}/history", response_model=list[MaintenanceHistoryEntry])
async def maintenance_history(
    service_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
    _: TokenPayload = Depends(require_permission("metrics:read")),
):
    return await maintenance.history(service_id=service_id, limit=limit)
