import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from platform_common.exceptions import NotFoundError
from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_metrics_service
from app.schemas.metric import (
    AggregationFunction,
    LatestMetricResponse,
    MetricIngestRequest,
    MetricIngestResponse,
    MetricQueryResponse,
)
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.post("/ingest", response_model=MetricIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_metric(
    body: MetricIngestRequest,
    metrics: MetricsService = Depends(get_metrics_service),
    _: TokenPayload = Depends(require_permission("metrics:write")),
):
    """
    Fallback REST ingestion path. The Kafka consumer (see app/workers) is
    the primary path for real telemetry volume — this exists for agents
    or ad-hoc callers that can't produce to Kafka directly.
    """
    metric = await metrics.ingest(
        service_id=body.service_id,
        metric_name=body.metric_name,
        value=body.value,
        labels=body.labels,
        timestamp=body.timestamp,
    )
    return MetricIngestResponse(accepted=True, time=metric.time)


@router.get("/query", response_model=MetricQueryResponse)
async def query_metrics(
    service_id: uuid.UUID,
    metric_name: str,
    start: datetime,
    end: datetime,
    aggregation: AggregationFunction = Query(default=AggregationFunction.AVG),
    interval_seconds: int = Query(default=60, ge=1),
    metrics: MetricsService = Depends(get_metrics_service),
    _: TokenPayload = Depends(require_permission("metrics:read")),
):
    points = await metrics.query(
        service_id=service_id,
        metric_name=metric_name,
        start=start,
        end=end,
        aggregation=aggregation,
        interval_seconds=interval_seconds,
    )
    return MetricQueryResponse(
        service_id=service_id,
        metric_name=metric_name,
        aggregation=aggregation,
        interval_seconds=interval_seconds,
        points=points,
    )


@router.get("/latest", response_model=LatestMetricResponse)
async def latest_metric(
    service_id: uuid.UUID,
    metric_name: str,
    metrics: MetricsService = Depends(get_metrics_service),
    _: TokenPayload = Depends(require_permission("metrics:read")),
):
    metric = await metrics.latest(service_id=service_id, metric_name=metric_name)
    if metric is None:
        raise NotFoundError(f"No data for metric '{metric_name}' on service '{service_id}'")
    return LatestMetricResponse(
        service_id=metric.service_id, metric_name=metric.metric_name, value=metric.value, time=metric.time
    )
