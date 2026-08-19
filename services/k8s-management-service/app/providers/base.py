"""
ClusterProvider: the abstraction boundary between "how we talk to a
cluster" and "everything else this service does" (REST handlers, scaling-
history recording, periodic snapshots — see services/k8s_service.py).

WHY this exists as an explicit interface rather than importing the
`kubernetes` client directly in the service layer: it's what makes
DemoClusterProvider (app/providers/demo_provider.py) a legitimate,
first-class implementation rather than a test-only hack — the service
layer, including every REST endpoint and the snapshot job, cannot tell
which provider it's talking to, and neither can the test suite. This is
the same reasoning as the platform's DB/message-broker abstractions: code
against an interface, swap the implementation per environment.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class NodeInfo:
    name: str
    status: str  # "Ready" | "NotReady"
    cpu_capacity: str
    memory_capacity: str
    region: str | None = None


@dataclass
class PodInfo:
    name: str
    namespace: str
    node_name: str | None
    status: str  # "Running" | "Pending" | "Failed" | "Succeeded" | "Unknown"
    restart_count: int
    service_name: str | None = None  # best-effort label-derived association


@dataclass
class DeploymentInfo:
    name: str
    namespace: str
    desired_replicas: int
    available_replicas: int
    updated_replicas: int


class ClusterProvider(Protocol):
    async def list_nodes(self) -> list[NodeInfo]: ...

    async def list_pods(self, namespace: str | None = None) -> list[PodInfo]: ...

    async def list_deployments(self, namespace: str | None = None) -> list[DeploymentInfo]: ...

    async def scale_deployment(self, *, namespace: str, name: str, replicas: int) -> DeploymentInfo: ...

    async def snapshot_time(self) -> datetime: ...
