import uuid
from datetime import datetime

from pydantic import BaseModel


class MaintenancePredictionResponse(BaseModel):
    service_id: uuid.UUID
    failure_probability: float
    root_cause: str
    recommendation: str
    feature_snapshot: dict


class MaintenanceHistoryEntry(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    failure_probability: float
    root_cause: str
    recommendation: str
    created_at: datetime

    model_config = {"from_attributes": True}
