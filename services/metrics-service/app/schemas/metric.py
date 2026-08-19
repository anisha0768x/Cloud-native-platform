import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AggregationFunction(str, Enum):
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    P95 = "p95"
    P99 = "p99"
    SUM = "sum"
    COUNT = "count"


class MetricIngestRequest(BaseModel):
    service_id: uuid.UUID
    metric_name: str = Field(min_length=1, max_length=100)
    value: float
    labels: dict | None = None
    timestamp: datetime | None = Field(
        default=None, description="Defaults to ingestion time if omitted"
    )


class MetricIngestResponse(BaseModel):
    accepted: bool
    time: datetime


class MetricQueryPoint(BaseModel):
    bucket_start: datetime
    value: float


class MetricQueryResponse(BaseModel):
    service_id: uuid.UUID
    metric_name: str
    aggregation: AggregationFunction
    interval_seconds: int
    points: list[MetricQueryPoint]


class LatestMetricResponse(BaseModel):
    service_id: uuid.UUID
    metric_name: str
    value: float
    time: datetime
