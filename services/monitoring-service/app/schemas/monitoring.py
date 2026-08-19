import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.monitoring import AlertSeverity, AlertStatus, ServiceStatus


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    type: str = Field(min_length=1, max_length=50)
    namespace: str = Field(default="default", max_length=100)
    owner_team: str | None = None


class ServiceUpdateRequest(BaseModel):
    type: str | None = None
    namespace: str | None = None
    owner_team: str | None = None


class ServiceResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    namespace: str
    owner_team: str | None
    status: ServiceStatus
    consecutive_failed_heartbeats: int
    last_heartbeat_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class HeartbeatRequest(BaseModel):
    healthy: bool
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None


class HeartbeatResponse(BaseModel):
    service_status: ServiceStatus
    consecutive_failed_heartbeats: int
    alert_created: bool


class HealthSummaryResponse(BaseModel):
    service_id: uuid.UUID
    current_status: ServiceStatus
    uptime_percentage: float
    checks_considered: int
    last_heartbeat_at: datetime | None


class AlertCreateRequest(BaseModel):
    service_id: uuid.UUID
    severity: AlertSeverity
    type: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)


class AlertResponse(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    severity: AlertSeverity
    type: str
    message: str
    status: AlertStatus
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
