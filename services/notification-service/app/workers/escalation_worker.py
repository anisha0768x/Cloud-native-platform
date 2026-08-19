"""
Periodic escalation loop, same sleep-loop pattern as K8s Management
Service's snapshot worker (Module 6) and Metrics Service's Kafka consumer
(Module 5) — one recurring job doesn't justify a scheduling library.

Re-sends any notification still `pending` (never acknowledged) past
ESCALATION_WINDOW_MINUTES through the SAME configured channels, marked
as an escalation delivery attempt, then flips its status to `escalated`
so it isn't re-escalated every poll cycle.
"""

import asyncio
from datetime import timedelta

from platform_common.db import Database
from platform_common.logging import get_logger

from app.channels.base import NotificationPayload
from app.repositories.notification_repository import NotificationRepository
from app.services.dispatcher import NotificationDispatcher

logger = get_logger(__name__)


async def run_escalation_worker(
    *, dispatcher: NotificationDispatcher, db: Database, window_minutes: int, poll_seconds: int
) -> None:
    logger.info("escalation worker started", extra={"window_minutes": window_minutes})
    while True:
        try:
            async with db.session_scope() as session:
                repo = NotificationRepository(session)
                overdue = await repo.find_overdue_for_escalation(window=timedelta(minutes=window_minutes))

                for notification in overdue:
                    payload = NotificationPayload(
                        service_id=notification.service_id,
                        severity=notification.severity,
                        message=f"[ESCALATED - unacknowledged after {window_minutes}m] {notification.message}",
                        alert_id=notification.alert_id,
                    )
                    results = await dispatcher.dispatch(payload)
                    for result in results:
                        await repo.add_delivery_attempt(
                            notification_id=notification.id,
                            channel=result.channel,
                            success=result.success,
                            error=result.error,
                            is_escalation=True,
                        )
                    await repo.mark_escalated(notification)
                    logger.info("escalated notification", extra={"notification_id": str(notification.id)})
        except Exception:
            logger.exception("escalation worker iteration failed")

        await asyncio.sleep(poll_seconds)
