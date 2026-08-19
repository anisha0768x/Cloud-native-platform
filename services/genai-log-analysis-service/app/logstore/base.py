"""
LogStore: abstracts "where logs are stored and searched" the same way
Module 6's ClusterProvider abstracted cluster access. Two implementations:

  - InMemoryLogStore (default): a process-local list with linear-scan
    filtering. Fine for local dev/testing/small demo volumes; obviously
    not what a real deployment uses for real log volume.
  - OpenSearchLogStore: real implementation against OpenSearch (the
    container already provisioned in infra/docker-compose.yml). Correct,
    reviewable code — but OpenSearch itself isn't installable in this
    sandbox (JVM-based, its package repo isn't in the allowed egress
    list), so this implementation is untestable live here, same honest
    limitation as Kafka in Module 5.

Every endpoint and the GenAI analysis logic are written against this
interface, so LOG_STORE_MODE is the only thing that changes to go from
local dev to a real OpenSearch-backed deployment.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class LogEntry:
    service_id: str
    level: str  # "DEBUG" | "INFO" | "WARNING" | "ERROR"
    message: str
    timestamp: datetime
    trace_id: str | None = None
    pod_id: str | None = None


class LogStore(Protocol):
    async def index(self, entry: LogEntry) -> None: ...

    async def search(
        self,
        *,
        service_id: str | None = None,
        level: str | None = None,
        query: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[LogEntry]: ...

    async def recent_errors(self, *, service_id: str, limit: int = 20) -> list[LogEntry]: ...
