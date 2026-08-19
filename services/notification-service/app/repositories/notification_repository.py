import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import DeliveryAttempt, Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, *, alert_id: str | None, service_id: str, severity: str, message: str) -> Notification:
        notification = Notification(alert_id=alert_id, service_id=service_id, severity=severity, message=message)
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def add_delivery_attempt(
        self, *, notification_id: uuid.UUID, channel: str, success: bool, error: str | None, is_escalation: bool = False
    ) -> DeliveryAttempt:
        attempt = DeliveryAttempt(
            notification_id=notification_id, channel=channel, success=success, error=error, is_escalation=is_escalation
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        result = await self._session.execute(select(Notification).where(Notification.id == notification_id))
        return result.scalar_one_or_none()

    async def acknowledge(self, notification: Notification) -> Notification:
        notification.status = "acknowledged"
        notification.acknowledged_at = datetime.now(timezone.utc)
        await self._session.flush()
        return notification

    async def mark_escalated(self, notification: Notification) -> Notification:
        notification.status = "escalated"
        notification.escalated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return notification

    async def find_overdue_for_escalation(self, *, window: timedelta) -> list[Notification]:
        cutoff = datetime.now(timezone.utc) - window
        query = select(Notification).where(
            Notification.status == "pending",
            Notification.created_at <= cutoff,
        )
        result = await self._session.execute(query)
        return list(result.scalars())

    async def history(
        self, *, service_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[Notification]:
        query = select(Notification)
        if service_id:
            query = query.where(Notification.service_id == service_id)
        if status:
            query = query.where(Notification.status == status)
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars())
