import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TrafficPredictionResponse(BaseModel):
    service_id: uuid.UUID
    horizon_hours: int
    expected_requests: float
    confidence_lower: float
    confidence_upper: float
    recommended_replicas: int
    data_source: str = Field(description="'historical' if trained on real Metrics Service data, else 'synthetic'")
    predicted_for: datetime


class PredictionHistoryEntry(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    horizon_hours: int
    expected_requests: float
    confidence_lower: float
    confidence_upper: float
    recommended_replicas: int
    data_source: str
    created_at: datetime

    model_config = {"from_attributes": True}
