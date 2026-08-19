import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import HealthCheckRecord, Service


class ServiceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, service_id: uuid.UUID) -> Service | None:
        result = await self._session.execute(select(Service).where(Service.id == service_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Service | None:
        result = await self._session.execute(select(Service).where(Service.name == name))
        return result.scalar_one_or_none()

    async def list_all(self, *, status: str | None = None, namespace: str | None = None) -> list[Service]:
        query = select(Service)
        if status:
            query = query.where(Service.status == status)
        if namespace:
            query = query.where(Service.namespace == namespace)
        result = await self._session.execute(query.order_by(Service.name))
        return list(result.scalars())

    async def create(self, **kwargs) -> Service:
        service = Service(**kwargs)
        self._session.add(service)
        await self._session.flush()
        return service

    async def delete(self, service: Service) -> None:
        await self._session.delete(service)

    async def add_health_check(
        self, *, service_id: uuid.UUID, healthy: bool, latency_ms: int | None, detail: str | None
    ) -> HealthCheckRecord:
        record = HealthCheckRecord(service_id=service_id, healthy=healthy, latency_ms=latency_ms, detail=detail)
        self._session.add(record)
        await self._session.flush()
        return record

    async def recent_health_checks(self, service_id: uuid.UUID, limit: int) -> list[HealthCheckRecord]:
        query = (
            select(HealthCheckRecord)
            .where(HealthCheckRecord.service_id == service_id)
            .order_by(HealthCheckRecord.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars())
