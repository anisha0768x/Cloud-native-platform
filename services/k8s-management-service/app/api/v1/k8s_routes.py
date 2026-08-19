from datetime import datetime

from fastapi import APIRouter, Depends, Query

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_k8s_service
from app.schemas.k8s import (
    ClusterSnapshotResponse,
    DeploymentResponse,
    NodeResponse,
    PodResponse,
    ScaleRequest,
    ScalingHistoryResponse,
)
from app.services.k8s_service import K8sService

router = APIRouter(prefix="/api/v1/k8s", tags=["kubernetes"])


@router.get("/nodes", response_model=list[NodeResponse])
async def list_nodes(
    k8s: K8sService = Depends(get_k8s_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await k8s.list_nodes()


@router.get("/pods", response_model=list[PodResponse])
async def list_pods(
    namespace: str | None = Query(default=None),
    k8s: K8sService = Depends(get_k8s_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await k8s.list_pods(namespace)


@router.get("/deployments", response_model=list[DeploymentResponse])
async def list_deployments(
    namespace: str | None = Query(default=None),
    k8s: K8sService = Depends(get_k8s_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await k8s.list_deployments(namespace)


@router.post("/deployments/{namespace}/{name}/scale", response_model=DeploymentResponse)
async def scale_deployment(
    namespace: str,
    name: str,
    body: ScaleRequest,
    k8s: K8sService = Depends(get_k8s_service),
    token: TokenPayload = Depends(require_permission("scaling:trigger")),
):
    return await k8s.scale_deployment(
        namespace=namespace, name=name, replicas=body.replicas, triggered_by=token.sub, trigger_source="manual"
    )


@router.get("/scaling-history", response_model=list[ScalingHistoryResponse])
async def scaling_history(
    namespace: str | None = Query(default=None),
    deployment_name: str | None = Query(default=None),
    k8s: K8sService = Depends(get_k8s_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await k8s.scaling_history(namespace=namespace, deployment_name=deployment_name)


@router.get("/snapshots", response_model=list[ClusterSnapshotResponse])
async def snapshots(
    start: datetime,
    end: datetime,
    k8s: K8sService = Depends(get_k8s_service),
    _: TokenPayload = Depends(require_permission("service:read")),
):
    return await k8s.snapshots(start=start, end=end)
