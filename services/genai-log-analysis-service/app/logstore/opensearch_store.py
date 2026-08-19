"""
Real OpenSearch-backed LogStore. Matches the master architecture doc's
§6.3 design: daily indices (`logs-YYYY.MM.DD`), which lets an ILM policy
(configured at the OpenSearch cluster level, not in application code) age
out old indices without the application needing to run delete queries.

NOT exercised by this service's test suite — OpenSearch requires a JVM
and isn't installable via this sandbox's allowed apt/pip mirrors. The
`infra/docker-compose.yml` OpenSearch container is the intended target;
this code is written to be correct against it, reviewed the same way the
Kubernetes provider in Module 6 was (real API calls, no live cluster to
verify against in this environment).
"""

from datetime import datetime

from opensearchpy import AsyncOpenSearch

from app.logstore.base import LogEntry


def _index_name(ts: datetime) -> str:
    return f"logs-{ts.strftime('%Y.%m.%d')}"


class OpenSearchLogStore:
    def __init__(self, hosts: list[str]):
        self._client = AsyncOpenSearch(hosts=hosts, use_ssl=False, verify_certs=False)

    async def index(self, entry: LogEntry) -> None:
        await self._client.index(
            index=_index_name(entry.timestamp),
            body={
                "service_id": entry.service_id,
                "level": entry.level,
                "message": entry.message,
                "timestamp": entry.timestamp.isoformat(),
                "trace_id": entry.trace_id,
                "pod_id": entry.pod_id,
            },
        )

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
        must: list[dict] = []
        if service_id:
            must.append({"term": {"service_id": service_id}})
        if level:
            must.append({"term": {"level": level}})
        if query:
            must.append({"match": {"message": query}})
        if start or end:
            range_filter: dict = {}
            if start:
                range_filter["gte"] = start.isoformat()
            if end:
                range_filter["lte"] = end.isoformat()
            must.append({"range": {"timestamp": range_filter}})

        body = {
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": limit,
        }

        result = await self._client.search(index="logs-*", body=body)
        hits = result.get("hits", {}).get("hits", [])
        return [
            LogEntry(
                service_id=h["_source"]["service_id"],
                level=h["_source"]["level"],
                message=h["_source"]["message"],
                timestamp=datetime.fromisoformat(h["_source"]["timestamp"]),
                trace_id=h["_source"].get("trace_id"),
                pod_id=h["_source"].get("pod_id"),
            )
            for h in hits
        ]

    async def recent_errors(self, *, service_id: str, limit: int = 20) -> list[LogEntry]:
        return await self.search(service_id=service_id, level="ERROR", limit=limit)
