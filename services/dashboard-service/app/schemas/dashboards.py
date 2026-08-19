from pydantic import BaseModel, Field


class ExecutiveDashboardResponse(BaseModel):
    total_services: int
    services_by_status: dict[str, int]
    overall_health_percentage: float
    open_alerts_by_severity: dict[str, int]
    cluster_node_count: int
    cluster_deployment_count: int
    cluster_pod_count: int
    partial_errors: list[str] = Field(
        default_factory=list, description="Backend calls that failed; other fields still reflect what succeeded"
    )


class ServiceHealthSummary(BaseModel):
    name: str
    status: str
    namespace: str


class InfrastructureDashboardResponse(BaseModel):
    nodes: list[dict]
    services_health: list[ServiceHealthSummary]
    cluster_snapshot_trend: list[dict]
    partial_errors: list[str] = Field(default_factory=list)


class KubernetesDashboardResponse(BaseModel):
    nodes: list[dict]
    pods: list[dict]
    deployments: list[dict]
    recent_scaling_history: list[dict]
    partial_errors: list[str] = Field(default_factory=list)
