"""
WHY raw SQL for the aggregation query instead of SQLAlchemy's query
builder: time-bucketing (`date_trunc`-style grouping into fixed intervals)
and percentile aggregation (`percentile_cont`) are exactly the kind of
DB-native operations the ORM's expression language doesn't model well —
forcing it through the ORM would produce less readable code for no
benefit. This is also exactly the kind of query TimescaleDB's
`time_bucket()` function is built to accelerate; using standard
`date_trunc`-style bucketing here means this same query runs correctly on
both plain Postgres (this sandbox) and real TimescaleDB, upgrading
transparently to use Timescale's continuous aggregates later without an
application-code change.
"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metric import Metric
from app.schemas.metric import AggregationFunction, MetricQueryPoint

_AGG_SQL = {
    AggregationFunction.AVG: "AVG(value)",
    AggregationFunction.MIN: "MIN(value)",
    AggregationFunction.MAX: "MAX(value)",
    AggregationFunction.SUM: "SUM(value)",
    AggregationFunction.COUNT: "COUNT(value)",
    AggregationFunction.P95: "PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value)",
    AggregationFunction.P99: "PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY value)",
}


class MetricRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def insert(
        self,
        *,
        service_id: uuid.UUID,
        metric_name: str,
        value: float,
        labels: dict | None,
        time: datetime,
    ) -> Metric:
        metric = Metric(service_id=service_id, metric_name=metric_name, value=value, labels=labels, time=time)
        self._session.add(metric)
        await self._session.flush()
        return metric

    async def query_aggregated(
        self,
        *,
        service_id: uuid.UUID,
        metric_name: str,
        start: datetime,
        end: datetime,
        aggregation: AggregationFunction,
        interval_seconds: int,
    ) -> list[MetricQueryPoint]:
        agg_expr = _AGG_SQL[aggregation]
        # Bucket boundaries are computed as whole-second offsets from the
        # query's own start time, not calendar-aligned — this keeps
        # bucketing correct regardless of interval_seconds (a calendar
        # date_trunc only has fixed granularities like 'hour'/'day').
        query = text(
            f"""
            SELECT
                to_timestamp(
                    floor(extract(epoch FROM time - :start) / :interval_seconds) * :interval_seconds
                    + extract(epoch FROM :start)
                ) AS bucket_start,
                {agg_expr} AS agg_value
            FROM metrics
            WHERE service_id = :service_id
              AND metric_name = :metric_name
              AND time >= :start
              AND time < :end
            GROUP BY bucket_start
            ORDER BY bucket_start
            """
        )
        result = await self._session.execute(
            query,
            {
                "service_id": str(service_id),
                "metric_name": metric_name,
                "start": start,
                "end": end,
                "interval_seconds": interval_seconds,
            },
        )
        return [MetricQueryPoint(bucket_start=row.bucket_start, value=row.agg_value) for row in result]

    async def latest(self, *, service_id: uuid.UUID, metric_name: str) -> Metric | None:
        from sqlalchemy import select

        query = (
            select(Metric)
            .where(Metric.service_id == service_id, Metric.metric_name == metric_name)
            .order_by(Metric.time.desc())
            .limit(1)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()
