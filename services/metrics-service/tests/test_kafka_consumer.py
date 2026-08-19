"""
NOTE ON SCOPE: a real Kafka broker isn't installable in this sandbox (no
Docker daemon, no JVM available via the allowed apt mirrors) — the local
dev docker-compose (infra/docker-compose.yml) already provisions Kafka
for real use. What CAN and SHOULD be tested here without a broker is the
handler logic itself: given a raw event dict (exactly what EventConsumer
would hand it after deserializing a Kafka message), does it correctly
write to the database, and does it correctly SURVIVE a malformed message
without crashing the consumer loop? That's the actual business logic;
the Kafka wiring around it is a thin, already-tested (in platform_common)
wrapper.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.repositories.metric_repository import MetricRepository
from app.workers.metrics_consumer import handle_metric_event

pytestmark = pytest.mark.asyncio


class _FakeDatabase:
    """Matches Database's session_scope() interface using a shared test session."""

    def __init__(self, session):
        self._session = session

    def session_scope(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _scope():
            yield self._session

        return _scope()


async def test_handler_writes_valid_metric_event_to_db(db_session):
    fake_db = _FakeDatabase(db_session)
    service_id = uuid.uuid4()
    event = {
        "event_type": "metric.recorded",
        "payload": {
            "service_id": str(service_id),
            "metric_name": "cpu_usage",
            "value": 73.5,
            "labels": {"pod": "checkout-api-abc123"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    await handle_metric_event(event, db=fake_db, max_query_range_days=90)

    repo = MetricRepository(db_session)
    latest = await repo.latest(service_id=service_id, metric_name="cpu_usage")
    assert latest is not None
    assert latest.value == 73.5
    assert latest.labels == {"pod": "checkout-api-abc123"}


async def test_handler_defaults_missing_timestamp_to_now(db_session):
    fake_db = _FakeDatabase(db_session)
    service_id = uuid.uuid4()
    event = {"payload": {"service_id": str(service_id), "metric_name": "memory_pct", "value": 10.0}}

    before = datetime.now(timezone.utc)
    await handle_metric_event(event, db=fake_db, max_query_range_days=90)
    after = datetime.now(timezone.utc)

    repo = MetricRepository(db_session)
    latest = await repo.latest(service_id=service_id, metric_name="memory_pct")
    assert before <= latest.time <= after


async def test_handler_drops_malformed_event_without_raising(db_session):
    """
    A malformed message must be skipped, NOT raise — an uncaught exception
    here would kill the consumer loop for every well-formed event queued
    behind it in the partition.
    """
    fake_db = _FakeDatabase(db_session)
    malformed_event = {"payload": {"metric_name": "cpu_usage"}}  # missing service_id and value

    await handle_metric_event(malformed_event, db=fake_db, max_query_range_days=90)  # must not raise


async def test_handler_drops_event_with_invalid_uuid(db_session):
    fake_db = _FakeDatabase(db_session)
    event = {"payload": {"service_id": "not-a-uuid", "metric_name": "cpu_usage", "value": 1.0}}

    await handle_metric_event(event, db=fake_db, max_query_range_days=90)  # must not raise
