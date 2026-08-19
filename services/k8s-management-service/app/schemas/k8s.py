import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NodeResponse(BaseModel):
    name: str
    status: str
    cpu_capacity: str
    memory_capacity: str
    region: str | None


class PodResponse(BaseModel):
    name: str
    namespace: str
    node_name: str | None
    status: str
    restart_count: int
    service_name: str | None


class DeploymentResponse(BaseModel):
    name: str
    namespace: str
    desired_replicas: int
    available_replicas: int
    updated_replicas: int


class ScaleRequest(BaseModel):
    replicas: int = Field(ge=0, le=100)


class ScalingHistoryResponse(BaseModel):
    id: uuid.UUID
    namespace: str
    deployment_name: str
    from_replicas: int
    to_replicas: int
    triggered_by: str
    trigger_source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ClusterSnapshotResponse(BaseModel):
    time: datetime
    node_count: int
    pod_count: int
    pods_running: int
    pods_pending: int
    pods_failed: int
    deployment_count: int

    model_config = {"from_attributes": True}
