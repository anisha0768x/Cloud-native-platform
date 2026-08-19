from app.logstore.base import LogEntry, LogStore
from app.logstore.in_memory import InMemoryLogStore


def build_log_store(mode: str, opensearch_hosts: list[str] | None = None) -> LogStore:
    if mode == "opensearch":
        from app.logstore.opensearch_store import OpenSearchLogStore

        return OpenSearchLogStore(hosts=opensearch_hosts or [])
    return InMemoryLogStore()


__all__ = ["LogStore", "LogEntry", "InMemoryLogStore", "build_log_store"]
