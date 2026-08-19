import uuid
from datetime import datetime, timedelta, timezone

from platform_common.exceptions import ValidationError

from app.models.metric import Metric
from app.repositories.metric_repository import MetricRepository
from app.schemas.metric import AggregationFunction, MetricQueryPoint


class MetricsService:
    def __init__(self, repo: MetricRepository, *, max_query_range_days: int):
        self._repo = repo
        self._max_range = timedelta(days=max_query_range_days)

    async def ingest(
        self, *, service_id: uuid.UUID, metric_name: str, value: float, labels: dict | None, timestamp: datetime | None
    ) -> Metric:
        point_time = timestamp or datetime.now(timezone.utc)
        return await self._repo.insert(
            service_id=service_id, metric_name=metric_name, value=value, labels=labels, time=point_time
        )

    async def query(
        self,
        *,
        service_id: uuid.UUID,
        metric_name: str,
        start: datetime,
        end: datetime,
        aggregation: AggregationFunction,
        interval_seconds: int,
    ) -> list[MetricQueryPoint]:
        if end <= start:
            raise ValidationError("'end' must be after 'start'")
        if end - start > self._max_range:
            raise ValidationError(
                f"Query range exceeds the maximum of {self._max_range.days} days",
                details={"requested_days": (end - start).days},
            )
        if interval_seconds < 1:
            raise ValidationError("'interval_seconds' must be at least 1")

        return await self._repo.query_aggregated(
            service_id=service_id,
            metric_name=metric_name,
            start=start,
            end=end,
            aggregation=aggregation,
            interval_seconds=interval_seconds,
        )

    async def latest(self, *, service_id: uuid.UUID, metric_name: str) -> Metric | None:
        return await self._repo.latest(service_id=service_id, metric_name=metric_name)
