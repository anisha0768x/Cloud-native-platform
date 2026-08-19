import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SendNotificationRequest(BaseModel):
    service_id: str = Field(min_length=1)
    severity: str = Field(pattern="^(info|warning|critical)$")
    message: str = Field(min_length=1)
    alert_id: str | None = None


class DeliveryAttemptResponse(BaseModel):
    channel: str
    success: bool
    error: str | None
    is_escalation: bool

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    id: uuid.UUID
    alert_id: str | None
    service_id: str
    severity: str
    message: str
    status: str
    acknowledged_at: datetime | None
    escalated_at: datetime | None
    created_at: datetime
    delivery_attempts: list[DeliveryAttemptResponse]

    model_config = {"from_attributes": True}
