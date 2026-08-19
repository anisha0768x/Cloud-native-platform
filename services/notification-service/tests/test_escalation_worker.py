"""
Tests the escalation worker's core logic directly (calling repository/
dispatcher methods against the real test DB) rather than waiting for the
actual sleep-loop to fire — same reasoning as testing Kafka consumer
handlers directly in Module 5: the LOOP is trivial (sleep + call), the
LOGIC (find overdue, re-dispatch, mark escalated) is what needs coverage.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.channels.base import DeliveryResult, NotificationPayload
from app.repositories.notification_repository import NotificationRepository
from app.services.dispatcher import NotificationDispatcher

pytestmark = pytest.mark.asyncio


class _FakeChannel:
    name = "fake"

    def __init__(self):
        self.sent: list[NotificationPayload] = []

    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        self.sent.append(payload)
        return DeliveryResult(channel=self.name, success=True)


async def test_overdue_pending_notification_is_found_for_escalation(db_session):
    repo = NotificationRepository(db_session)
    notification = await repo.create(alert_id="a1", service_id="svc-x", severity="critical", message="down")

    # Backdate created_at past the escalation window directly (simulating
    # time passing, without actually sleeping in the test).
    notification.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    await db_session.flush()

    overdue = await repo.find_overdue_for_escalation(window=timedelta(minutes=15))
    assert len(overdue) == 1
    assert overdue[0].id == notification.id


async def test_recent_pending_notification_is_not_yet_overdue(db_session):
    repo = NotificationRepository(db_session)
    await repo.create(alert_id="a2", service_id="svc-y", severity="critical", message="down")
    # created_at defaults to now — well within the 15-minute window.

    overdue = await repo.find_overdue_for_escalation(window=timedelta(minutes=15))
    assert len(overdue) == 0


async def test_acknowledged_notification_is_never_escalated(db_session):
    repo = NotificationRepository(db_session)
    notification = await repo.create(alert_id="a3", service_id="svc-z", severity="critical", message="down")
    notification.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    await db_session.flush()
    await repo.acknowledge(notification)

    overdue = await repo.find_overdue_for_escalation(window=timedelta(minutes=15))
    assert len(overdue) == 0  # acknowledged, not pending — must not re-fire


async def test_escalation_dispatch_and_mark_flow(db_session):
    """Exercises the exact sequence app/workers/escalation_worker.py runs per overdue notification."""
    repo = NotificationRepository(db_session)
    notification = await repo.create(alert_id="a4", service_id="svc-w", severity="critical", message="still down")
    notification.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    await db_session.flush()

    fake_channel = _FakeChannel()
    dispatcher = NotificationDispatcher([fake_channel])

    payload = NotificationPayload(
        service_id=notification.service_id, severity=notification.severity,
        message=f"[ESCALATED] {notification.message}", alert_id=notification.alert_id,
    )
    results = await dispatcher.dispatch(payload)
    for result in results:
        await repo.add_delivery_attempt(
            notification_id=notification.id, channel=result.channel, success=result.success,
            error=result.error, is_escalation=True,
        )
    updated = await repo.mark_escalated(notification)

    assert updated.status == "escalated"
    assert updated.escalated_at is not None
    assert len(fake_channel.sent) == 1
    assert "[ESCALATED]" in fake_channel.sent[0].message

    # No longer found as overdue-pending (status changed away from "pending").
    overdue = await repo.find_overdue_for_escalation(window=timedelta(minutes=15))
    assert notification.id not in [n.id for n in overdue]
