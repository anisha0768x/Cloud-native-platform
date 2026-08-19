import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import LogAnalysis


class AnalysisRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record(self, **kwargs) -> LogAnalysis:
        analysis = LogAnalysis(**kwargs)
        self._session.add(analysis)
        await self._session.flush()
        return analysis

    async def history(self, *, service_id: uuid.UUID, limit: int = 50) -> list[LogAnalysis]:
        query = (
            select(LogAnalysis)
            .where(LogAnalysis.service_id == service_id)
            .order_by(LogAnalysis.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars())
