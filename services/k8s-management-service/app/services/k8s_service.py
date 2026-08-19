from datetime import datetime

from app.providers.base import ClusterProvider, DeploymentInfo
from app.repositories.k8s_repository import K8sRepository


class K8sService:
    def __init__(self, provider: ClusterProvider, repo: K8sRepository):
        self._provider = provider
        self._repo = repo

    async def list_nodes(self):
        return await self._provider.list_nodes()

    async def list_pods(self, namespace: str | None = None):
        return await self._provider.list_pods(namespace)

    async def list_deployments(self, namespace: str | None = None):
        return await self._provider.list_deployments(namespace)

    async def scale_deployment(
        self, *, namespace: str, name: str, replicas: int, triggered_by: str, trigger_source: str = "manual"
    ) -> DeploymentInfo:
        # Read current state FIRST so scaling_history records an accurate
        # from_replicas — reading it after the scale call would make every
        # entry show from==to, which defeats the point of an audit trail.
        current = await self._provider.list_deployments(namespace)
        existing = next((d for d in current if d.name == name), None)
        from_replicas = existing.desired_replicas if existing else 0

        updated = await self._provider.scale_deployment(namespace=namespace, name=name, replicas=replicas)

        await self._repo.record_scaling_action(
            namespace=namespace,
            deployment_name=name,
            from_replicas=from_replicas,
            to_replicas=replicas,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
        )
        return updated

    async def scaling_history(self, *, namespace: str | None = None, deployment_name: str | None = None):
        return await self._repo.list_scaling_history(namespace=namespace, deployment_name=deployment_name)

    async def capture_snapshot(self):
        """
        Called by the periodic background worker (see
        app/workers/snapshot_worker.py). Deliberately queries the provider
        fresh each time rather than reusing list_pods/list_deployments
        results from elsewhere — this is meant to run standalone on a
        timer, independent of any request.
        """
        nodes = await self._provider.list_nodes()
        pods = await self._provider.list_pods()
        deployments = await self._provider.list_deployments()

        return await self._repo.record_snapshot(
            time=await self._provider.snapshot_time(),
            node_count=len(nodes),
            pod_count=len(pods),
            pods_running=sum(1 for p in pods if p.status == "Running"),
            pods_pending=sum(1 for p in pods if p.status == "Pending"),
            pods_failed=sum(1 for p in pods if p.status == "Failed"),
            deployment_count=len(deployments),
        )

    async def snapshots(self, *, start: datetime, end: datetime):
        return await self._repo.list_snapshots(start=start, end=end)
