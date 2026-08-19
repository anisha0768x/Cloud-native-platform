import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maintenance import MaintenancePrediction


class MaintenancePredictionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record(self, **kwargs) -> MaintenancePrediction:
        prediction = MaintenancePrediction(**kwargs)
        self._session.add(prediction)
        await self._session.flush()
        return prediction

    async def history(self, *, service_id: uuid.UUID, limit: int = 50) -> list[MaintenancePrediction]:
        query = (
            select(MaintenancePrediction)
            .where(MaintenancePrediction.service_id == service_id)
            .order_by(MaintenancePrediction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars())
