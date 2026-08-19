from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.k8s import ClusterSnapshot, ScalingHistory


class K8sRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_scaling_action(
        self,
        *,
        namespace: str,
        deployment_name: str,
        from_replicas: int,
        to_replicas: int,
        triggered_by: str,
        trigger_source: str = "manual",
    ) -> ScalingHistory:
        record = ScalingHistory(
            namespace=namespace,
            deployment_name=deployment_name,
            from_replicas=from_replicas,
            to_replicas=to_replicas,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_scaling_history(
        self, *, namespace: str | None = None, deployment_name: str | None = None, limit: int = 100
    ) -> list[ScalingHistory]:
        query = select(ScalingHistory)
        if namespace:
            query = query.where(ScalingHistory.namespace == namespace)
        if deployment_name:
            query = query.where(ScalingHistory.deployment_name == deployment_name)
        query = query.order_by(ScalingHistory.created_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars())

    async def record_snapshot(self, **kwargs) -> ClusterSnapshot:
        snapshot = ClusterSnapshot(**kwargs)
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def list_snapshots(self, *, start: datetime, end: datetime, limit: int = 1000) -> list[ClusterSnapshot]:
        query = (
            select(ClusterSnapshot)
            .where(ClusterSnapshot.time >= start, ClusterSnapshot.time < end)
            .order_by(ClusterSnapshot.time)
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars())
