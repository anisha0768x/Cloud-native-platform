from fastapi import APIRouter, Depends, Header

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_dashboard_service
from app.schemas.dashboards import (
    ExecutiveDashboardResponse,
    InfrastructureDashboardResponse,
    KubernetesDashboardResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])


@router.get("/executive", response_model=ExecutiveDashboardResponse)
async def executive_dashboard(
    authorization: str = Header(...),
    dashboards: DashboardService = Depends(get_dashboard_service),
    _: TokenPayload = Depends(require_permission("dashboard:read")),
):
    # `authorization` is forwarded AS-IS to backend calls — this is
    # delegated auth (see clients/backend_client.py's module docstring):
    # each backend independently re-verifies the same token rather than
    # trusting this service's RBAC check alone.
    return await dashboards.executive_dashboard(authorization)


@router.get("/infrastructure", response_model=InfrastructureDashboardResponse)
async def infrastructure_dashboard(
    authorization: str = Header(...),
    dashboards: DashboardService = Depends(get_dashboard_service),
    _: TokenPayload = Depends(require_permission("dashboard:read")),
):
    return await dashboards.infrastructure_dashboard(authorization)


@router.get("/kubernetes", response_model=KubernetesDashboardResponse)
async def kubernetes_dashboard(
    authorization: str = Header(...),
    dashboards: DashboardService = Depends(get_dashboard_service),
    _: TokenPayload = Depends(require_permission("dashboard:read")),
):
    return await dashboards.kubernetes_dashboard(authorization)
