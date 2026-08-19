from datetime import datetime

from app.logstore.base import LogEntry


class InMemoryLogStore:
    def __init__(self):
        self._entries: list[LogEntry] = []

    async def index(self, entry: LogEntry) -> None:
        self._entries.append(entry)

    async def search(
        self,
        *,
        service_id: str | None = None,
        level: str | None = None,
        query: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[LogEntry]:
        results = self._entries
        if service_id:
            results = [e for e in results if e.service_id == service_id]
        if level:
            results = [e for e in results if e.level == level]
        if query:
            results = [e for e in results if query.lower() in e.message.lower()]
        if start:
            results = [e for e in results if e.timestamp >= start]
        if end:
            results = [e for e in results if e.timestamp <= end]
        # Most recent first, matching how OpenSearch's real implementation
        # would sort (descending timestamp is the useful default for logs).
        results = sorted(results, key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    async def recent_errors(self, *, service_id: str, limit: int = 20) -> list[LogEntry]:
        return await self.search(service_id=service_id, level="ERROR", limit=limit)
