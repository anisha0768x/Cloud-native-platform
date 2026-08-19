"""
Background Kafka consumer: the PRIMARY ingestion path (the REST /ingest
endpoint in api/v1/metric_routes.py is the fallback, per the master
architecture doc's §1.1 rationale — telemetry writes shouldn't be coupled
to a synchronous REST round-trip from every producer).

Runs as an asyncio background task started in the app's lifespan, using
its OWN database session (independent of any request's session) since it
processes events outside of any HTTP request's lifecycle entirely.

WHY commit-after-write (not auto-commit) matters here: EventConsumer is
configured with enable_auto_commit=False (see platform_common's
EventConsumer), and this handler only lets the consumer loop commit the
Kafka offset AFTER the DB write succeeds — if the service crashes between
the DB write and the offset commit, Kafka will redeliver the message on
restart. That's an intentional at-least-once guarantee; ingest() is a
plain INSERT, so a rare duplicate row on redelivery is a far better
failure mode than silently losing a metric.
"""

import uuid
from datetime import datetime

from platform_common.db import Database
from platform_common.events import EventConsumer
from platform_common.logging import get_logger

from app.repositories.metric_repository import MetricRepository
from app.services.metrics_service import MetricsService

logger = get_logger(__name__)


async def handle_metric_event(event: dict, *, db: Database, max_query_range_days: int) -> None:
    payload = event.get("payload", {})
    try:
        service_id = uuid.UUID(payload["service_id"])
        metric_name = payload["metric_name"]
        value = float(payload["value"])
        labels = payload.get("labels")
        raw_ts = payload.get("timestamp")
        timestamp = datetime.fromisoformat(raw_ts) if raw_ts else None
    except (KeyError, ValueError, TypeError) as exc:
        # A malformed event must NOT crash the consumer loop (that would
        # stop ingestion for every well-formed event behind it in the
        # partition) — log and skip instead.
        logger.warning("dropping malformed metric event", extra={"error": str(exc), "event": event})
        return

    async with db.session_scope() as session:
        metrics_service = MetricsService(MetricRepository(session), max_query_range_days=max_query_range_days)
        await metrics_service.ingest(
            service_id=service_id, metric_name=metric_name, value=value, labels=labels, timestamp=timestamp
        )


async def run_metrics_consumer(
    *, bootstrap_servers: str, topic: str, group_id: str, db: Database, max_query_range_days: int
) -> None:
    consumer = EventConsumer(bootstrap_servers, [topic], group_id)
    await consumer.start()
    logger.info("metrics Kafka consumer started", extra={"topic": topic, "group_id": group_id})
    try:
        await consumer.run(
            lambda event: handle_metric_event(event, db=db, max_query_range_days=max_query_range_days)
        )
    finally:
        await consumer.stop()
