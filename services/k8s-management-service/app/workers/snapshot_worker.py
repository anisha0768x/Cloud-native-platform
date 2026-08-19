"""
Periodic snapshot loop — runs as an asyncio background task started in
the app's lifespan (same pattern as the Metrics Service's Kafka consumer
task). WHY a simple sleep-loop rather than a proper scheduler (Celery
beat, APScheduler): this service has exactly one recurring job at a fixed
interval — pulling in a scheduling library for that would be dependency
weight without a corresponding benefit. If a second recurring job appears
in a later module, that's the trigger to revisit this decision.
"""

import asyncio

from platform_common.db import Database
from platform_common.logging import get_logger

from app.providers.base import ClusterProvider
from app.repositories.k8s_repository import K8sRepository
from app.services.k8s_service import K8sService

logger = get_logger(__name__)


async def run_snapshot_worker(*, provider: ClusterProvider, db: Database, interval_seconds: int) -> None:
    logger.info("cluster snapshot worker started", extra={"interval_seconds": interval_seconds})
    while True:
        try:
            async with db.session_scope() as session:
                service = K8sService(provider, K8sRepository(session))
                snapshot = await service.capture_snapshot()
                logger.info(
                    "captured cluster snapshot",
                    extra={"pod_count": snapshot.pod_count, "node_count": snapshot.node_count},
                )
        except Exception:
            # A single failed snapshot (e.g. a transient API server blip)
            # must not kill the loop — log and try again next interval.
            logger.exception("cluster snapshot capture failed")

        await asyncio.sleep(interval_seconds)
