"""
Kafka consumer: primary log ingestion path (REST /api/v1/logs/ingest in
the API routes is the fallback), same reasoning as Metrics Service's
consumer — log volume is bursty and shouldn't couple every producer to a
synchronous REST round-trip.
"""

import uuid
from datetime import datetime

from platform_common.events import EventConsumer
from platform_common.logging import get_logger

from app.logstore.base import LogEntry, LogStore

logger = get_logger(__name__)


async def handle_log_event(event: dict, *, log_store: LogStore) -> None:
    payload = event.get("payload", {})
    try:
        entry = LogEntry(
            service_id=str(uuid.UUID(payload["service_id"])),
            level=payload["level"],
            message=payload["message"],
            timestamp=datetime.fromisoformat(payload["timestamp"]) if payload.get("timestamp") else datetime.now(),
            trace_id=payload.get("trace_id"),
            pod_id=payload.get("pod_id"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("dropping malformed log event", extra={"error": str(exc), "event": event})
        return

    await log_store.index(entry)


async def run_logs_consumer(
    *, bootstrap_servers: str, topic: str, group_id: str, log_store: LogStore
) -> None:
    consumer = EventConsumer(bootstrap_servers, [topic], group_id)
    await consumer.start()
    logger.info("logs Kafka consumer started", extra={"topic": topic, "group_id": group_id})
    try:
        await consumer.run(lambda event: handle_log_event(event, log_store=log_store))
    finally:
        await consumer.stop()
