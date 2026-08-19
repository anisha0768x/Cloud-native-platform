"""
Real cluster provider, backed by the official `kubernetes` Python client.

WHY asyncio.to_thread wrapping instead of an async K8s client library:
the official `kubernetes` package's client is synchronous. Rather than
add `kubernetes_asyncio` (a second, less widely maintained package with
its own subtle version-compatibility footguns against the same API) as a
dependency, each blocking call is wrapped in `asyncio.to_thread` — this
keeps the FastAPI event loop responsive without introducing a second K8s
client library, at the cost of a thread per in-flight call, which is a
fine trade-off at this service's call volume (cluster reads are cheap and
infrequent relative to a real request-serving hot path).

Config resolution: `kubernetes.config.load_incluster_config()` when
running as a Pod (reads the ServiceAccount token/CA mounted by K8s
automatically), falling back to `load_kube_config()` (reads
`~/.kube/config`) for local development against a real cluster (e.g.
minikube/kind) — this is the standard resolution order every kubectl-like
tool uses.
"""

import asyncio
from datetime import datetime, timezone

from kubernetes import client, config

from app.providers.base import DeploymentInfo, NodeInfo, PodInfo


def _load_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


class KubernetesClusterProvider:
    def __init__(self):
        _load_config()
        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()

    async def list_nodes(self) -> list[NodeInfo]:
        result = await asyncio.to_thread(self._core.list_node)
        nodes = []
        for n in result.items:
            ready = any(
                c.type == "Ready" and c.status == "True" for c in (n.status.conditions or [])
            )
            nodes.append(
                NodeInfo(
                    name=n.metadata.name,
                    status="Ready" if ready else "NotReady",
                    cpu_capacity=n.status.capacity.get("cpu", "unknown"),
                    memory_capacity=n.status.capacity.get("memory", "unknown"),
                    region=(n.metadata.labels or {}).get("topology.kubernetes.io/region"),
                )
            )
        return nodes

    async def list_pods(self, namespace: str | None = None) -> list[PodInfo]:
        if namespace:
            result = await asyncio.to_thread(self._core.list_namespaced_pod, namespace)
        else:
            result = await asyncio.to_thread(self._core.list_pod_for_all_namespaces)

        pods = []
        for p in result.items:
            restart_count = sum(cs.restart_count for cs in (p.status.container_statuses or []))
            pods.append(
                PodInfo(
                    name=p.metadata.name,
                    namespace=p.metadata.namespace,
                    node_name=p.spec.node_name,
                    status=p.status.phase or "Unknown",
                    restart_count=restart_count,
                    service_name=(p.metadata.labels or {}).get("app"),
                )
            )
        return pods

    async def list_deployments(self, namespace: str | None = None) -> list[DeploymentInfo]:
        if namespace:
            result = await asyncio.to_thread(self._apps.list_namespaced_deployment, namespace)
        else:
            result = await asyncio.to_thread(self._apps.list_deployment_for_all_namespaces)

        return [
            DeploymentInfo(
                name=d.metadata.name,
                namespace=d.metadata.namespace,
                desired_replicas=d.spec.replicas or 0,
                available_replicas=d.status.available_replicas or 0,
                updated_replicas=d.status.updated_replicas or 0,
            )
            for d in result.items
        ]

    async def scale_deployment(self, *, namespace: str, name: str, replicas: int) -> DeploymentInfo:
        patch = {"spec": {"replicas": replicas}}
        await asyncio.to_thread(
            self._apps.patch_namespaced_deployment_scale, name=name, namespace=namespace, body=patch
        )
        updated = await asyncio.to_thread(self._apps.read_namespaced_deployment, name=name, namespace=namespace)
        return DeploymentInfo(
            name=updated.metadata.name,
            namespace=updated.metadata.namespace,
            desired_replicas=updated.spec.replicas or 0,
            available_replicas=updated.status.available_replicas or 0,
            updated_replicas=updated.status.updated_replicas or 0,
        )

    async def snapshot_time(self) -> datetime:
        return datetime.now(timezone.utc)
