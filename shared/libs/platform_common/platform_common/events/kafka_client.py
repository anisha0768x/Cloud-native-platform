"""
Kafka producer/consumer wrappers.

WHY wrapped instead of using aiokafka directly in each service:
  - Standard JSON serialization (every event is `{"event_type", "occurred_at",
    "producer", "payload"}`) so consumers can be written generically and the
    event-schema registry (shared/event-schemas/) has one envelope to
    validate against, not 12 ad-hoc ones.
  - Producer retries + delivery confirmation configured once, correctly,
    matching the "at-least-once" guarantee assumed by every consumer's
    idempotent-write design (see Metrics Service design, §4.1).
  - A single place to add tracing/log correlation (trace_id propagated
    into the event envelope) so a request can be followed across the
    REST -> Kafka -> consumer boundary.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer


def _envelope(event_type: str, producer_service: str, payload: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "occurred_at": time.time(),
            "producer": producer_service,
            "payload": payload,
        }
    ).encode("utf-8")


class EventProducer:
    def __init__(self, bootstrap_servers: str, service_name: str):
        self._bootstrap_servers = bootstrap_servers
        self._service_name = service_name
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",  # wait for full ISR ack — durability over raw throughput
            enable_idempotence=True,  # prevents duplicate sends on producer retry
            linger_ms=10,  # small batching window, matters at metrics-ingestion volume
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def publish(self, topic: str, event_type: str, payload: dict[str, Any], key: str | None = None) -> None:
        if not self._producer:
            raise RuntimeError("EventProducer.start() was not called")
        value = _envelope(event_type, self._service_name, payload)
        await self._producer.send_and_wait(topic, value=value, key=key.encode() if key else None)


class EventConsumer:
    def __init__(self, bootstrap_servers: str, topics: list[str], group_id: str):
        self._bootstrap_servers = bootstrap_servers
        self._topics = topics
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            enable_auto_commit=False,  # manual commit after successful processing = at-least-once
            auto_offset_reset="earliest",
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()

    async def consume(self) -> AsyncIterator[dict[str, Any]]:
        if not self._consumer:
            raise RuntimeError("EventConsumer.start() was not called")
        async for msg in self._consumer:
            yield json.loads(msg.value.decode("utf-8"))
            await self._consumer.commit()

    async def run(self, handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        """Convenience loop: consume forever, calling handler per event."""
        async for event in self.consume():
            await handler(event)
