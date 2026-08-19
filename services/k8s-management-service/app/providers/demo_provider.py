"""
Demo cluster provider: generates realistic, INTERNALLY CONSISTENT synthetic
cluster state (fixed set of nodes/deployments, pods that actually belong
to those deployments/nodes) so every downstream feature — dashboards,
scaling actions, the periodic snapshot job — has real data to work with
without requiring a live Kubernetes cluster.

This is the DEFAULT provider (see core/config.py's CLUSTER_MODE). Scaling
actually mutates this in-memory state (desired_replicas changes, pod count
follows), so `POST /scale` behaves indistinguishably from the real
provider as far as every caller (REST client, tests, the scaling-history
recorder) can tell — which is exactly the point of coding to the
ClusterProvider interface.
"""

import random
from datetime import datetime, timezone

from app.providers.base import DeploymentInfo, NodeInfo, PodInfo

_NODE_NAMES = ["node-pool-general-1", "node-pool-general-2", "node-pool-compute-1"]

_DEPLOYMENTS: dict[tuple[str, str], dict] = {
    ("default", "checkout-api"): {"replicas": 3},
    ("default", "payments-api"): {"replicas": 2},
    ("monitoring", "grafana"): {"replicas": 1},
}


class DemoClusterProvider:
    def __init__(self):
        # Deliberately mutable instance state — a fresh provider per
        # process, seeded once, then mutated by scale_deployment() so
        # repeated queries within the same run stay internally consistent
        # (e.g. list_pods() reflects the last scale_deployment() call).
        self._deployments = {k: dict(v) for k, v in _DEPLOYMENTS.items()}

    async def list_nodes(self) -> list[NodeInfo]:
        return [
            NodeInfo(
                name=name,
                status="Ready",
                cpu_capacity="4",
                memory_capacity="16Gi",
                region="us-central1",
            )
            for name in _NODE_NAMES
        ]

    async def list_pods(self, namespace: str | None = None) -> list[PodInfo]:
        pods = []
        for (ns, dep_name), state in self._deployments.items():
            if namespace and ns != namespace:
                continue
            for i in range(state["replicas"]):
                pods.append(
                    PodInfo(
                        name=f"{dep_name}-{random.randint(1000,9999)}-{chr(97+i)}",
                        namespace=ns,
                        node_name=random.choice(_NODE_NAMES),
                        status="Running",
                        restart_count=0,
                        service_name=dep_name,
                    )
                )
        return pods

    async def list_deployments(self, namespace: str | None = None) -> list[DeploymentInfo]:
        result = []
        for (ns, name), state in self._deployments.items():
            if namespace and ns != namespace:
                continue
            result.append(
                DeploymentInfo(
                    name=name,
                    namespace=ns,
                    desired_replicas=state["replicas"],
                    available_replicas=state["replicas"],
                    updated_replicas=state["replicas"],
                )
            )
        return result

    async def scale_deployment(self, *, namespace: str, name: str, replicas: int) -> DeploymentInfo:
        key = (namespace, name)
        if key not in self._deployments:
            from platform_common.exceptions import NotFoundError

            raise NotFoundError(f"Deployment '{name}' not found in namespace '{namespace}'")
        self._deployments[key]["replicas"] = replicas
        return DeploymentInfo(
            name=name, namespace=namespace, desired_replicas=replicas, available_replicas=replicas, updated_replicas=replicas
        )

    async def snapshot_time(self) -> datetime:
        return datetime.now(timezone.utc)
