import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import Alert, AlertStatus


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        result = await self._session.execute(select(Alert).where(Alert.id == alert_id))
        return result.scalar_one_or_none()

    async def list_all(
        self, *, service_id: uuid.UUID | None = None, status: str | None = None, severity: str | None = None
    ) -> list[Alert]:
        query = select(Alert)
        if service_id:
            query = query.where(Alert.service_id == service_id)
        if status:
            query = query.where(Alert.status == status)
        if severity:
            query = query.where(Alert.severity == severity)
        result = await self._session.execute(query.order_by(Alert.created_at.desc()))
        return list(result.scalars())

    async def create(self, **kwargs) -> Alert:
        alert = Alert(**kwargs)
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def has_open_alert_of_type(self, service_id: uuid.UUID, alert_type: str) -> bool:
        """
        Prevents duplicate alert spam: if a service is already flapping
        down/up/down, we don't want a fresh 'service_down' alert on every
        single failure — only when transitioning INTO the down state with
        no existing open alert of that type.
        """
        result = await self._session.execute(
            select(Alert.id).where(
                Alert.service_id == service_id, Alert.type == alert_type, Alert.status == AlertStatus.OPEN
            )
        )
        return result.scalar_one_or_none() is not None

    async def acknowledge(self, alert: Alert, *, acknowledged_by: str) -> Alert:
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = datetime.now(timezone.utc)
        await self._session.flush()
        return alert

    async def resolve(self, alert: Alert) -> Alert:
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        await self._session.flush()
        return alert
