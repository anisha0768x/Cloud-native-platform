"""
DashboardService: the aggregation logic for each dashboard.

WHY cache-aside (check Redis, compute-and-store on miss) rather than a
write-through cache updated by events: dashboard reads are far more
frequent than the underlying data changes meaningfully (a service's
status doesn't need a sub-second-fresh dashboard), and cache-aside is
simpler to reason about — no risk of the cache silently drifting from
reality if an update event is ever missed, since it just re-fetches from
source of truth on expiry.
"""

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.clients.backend_client import BackendClient
from app.schemas.dashboards import (
    ExecutiveDashboardResponse,
    InfrastructureDashboardResponse,
    KubernetesDashboardResponse,
    ServiceHealthSummary,
)


class DashboardService:
    def __init__(
        self,
        monitoring: BackendClient,
        k8s: BackendClient,
        redis_client,
        *,
        cache_ttl_seconds: int,
    ):
        self._monitoring = monitoring
        self._k8s = k8s
        self._redis = redis_client
        self._ttl = cache_ttl_seconds

    async def _cached(self, key: str, model_cls, compute):
        """
        Cache key deliberately does NOT vary per calling user: dashboard
        data (service health, cluster state) is platform-wide operational
        state, not user-specific — RBAC (dashboard:read) already gates WHO
        can see it, but WHAT they see is identical for every authorized
        viewer. A shared cache key means the first dashboard load after
        expiry pays the aggregation cost once, not once per viewer.
        """
        cached = await self._redis.get(key)
        if cached:
            return model_cls.model_validate_json(cached)
        result = await compute()
        await self._redis.set(key, result.model_dump_json(), ex=self._ttl)
        return result

    async def executive_dashboard(self, authorization: str) -> ExecutiveDashboardResponse:
        async def compute() -> ExecutiveDashboardResponse:
            services, alerts, nodes, pods, deployments = await asyncio.gather(
                self._monitoring.get("/api/v1/services", authorization=authorization),
                self._monitoring.get("/api/v1/alerts", authorization=authorization, params={"status": "open"}),
                self._k8s.get("/api/v1/k8s/nodes", authorization=authorization),
                self._k8s.get("/api/v1/k8s/pods", authorization=authorization),
                self._k8s.get("/api/v1/k8s/deployments", authorization=authorization),
            )

            errors = []
            for name, value in [
                ("monitoring:services", services),
                ("monitoring:alerts", alerts),
                ("k8s:nodes", nodes),
                ("k8s:pods", pods),
                ("k8s:deployments", deployments),
            ]:
                if value is None:
                    errors.append(name)

            services = services or []
            alerts = alerts or []
            nodes = nodes or []
            pods = pods or []
            deployments = deployments or []

            status_counts = Counter(s["status"] for s in services)
            healthy_count = status_counts.get("healthy", 0)
            total = len(services)
            health_pct = round((healthy_count / total) * 100, 2) if total else 0.0

            severity_counts = Counter(a["severity"] for a in alerts)

            return ExecutiveDashboardResponse(
                total_services=total,
                services_by_status=dict(status_counts),
                overall_health_percentage=health_pct,
                open_alerts_by_severity=dict(severity_counts),
                cluster_node_count=len(nodes),
                cluster_deployment_count=len(deployments),
                cluster_pod_count=len(pods),
                partial_errors=errors,
            )

        return await self._cached("dashboard:executive", ExecutiveDashboardResponse, compute)

    async def infrastructure_dashboard(self, authorization: str) -> InfrastructureDashboardResponse:
        async def compute() -> InfrastructureDashboardResponse:
            now = datetime.now(timezone.utc)
            services, nodes, snapshots = await asyncio.gather(
                self._monitoring.get("/api/v1/services", authorization=authorization),
                self._k8s.get("/api/v1/k8s/nodes", authorization=authorization),
                self._k8s.get(
                    "/api/v1/k8s/snapshots",
                    authorization=authorization,
                    params={"start": (now - timedelta(hours=24)).isoformat(), "end": now.isoformat()},
                ),
            )

            errors = []
            for name, value in [("monitoring:services", services), ("k8s:nodes", nodes), ("k8s:snapshots", snapshots)]:
                if value is None:
                    errors.append(name)

            services = services or []
            nodes = nodes or []
            snapshots = snapshots or []

            return InfrastructureDashboardResponse(
                nodes=nodes,
                services_health=[
                    ServiceHealthSummary(name=s["name"], status=s["status"], namespace=s.get("namespace", "default"))
                    for s in services
                ],
                cluster_snapshot_trend=snapshots,
                partial_errors=errors,
            )

        return await self._cached("dashboard:infrastructure", InfrastructureDashboardResponse, compute)

    async def kubernetes_dashboard(self, authorization: str) -> KubernetesDashboardResponse:
        async def compute() -> KubernetesDashboardResponse:
            nodes, pods, deployments, history = await asyncio.gather(
                self._k8s.get("/api/v1/k8s/nodes", authorization=authorization),
                self._k8s.get("/api/v1/k8s/pods", authorization=authorization),
                self._k8s.get("/api/v1/k8s/deployments", authorization=authorization),
                self._k8s.get("/api/v1/k8s/scaling-history", authorization=authorization),
            )

            errors = []
            for name, value in [
                ("k8s:nodes", nodes),
                ("k8s:pods", pods),
                ("k8s:deployments", deployments),
                ("k8s:scaling-history", history),
            ]:
                if value is None:
                    errors.append(name)

            return KubernetesDashboardResponse(
                nodes=nodes or [],
                pods=pods or [],
                deployments=deployments or [],
                recent_scaling_history=(history or [])[:20],
                partial_errors=errors,
            )

        return await self._cached("dashboard:kubernetes", KubernetesDashboardResponse, compute)
