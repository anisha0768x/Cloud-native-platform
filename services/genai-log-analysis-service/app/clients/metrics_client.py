"""
Fetches a small correlated-metrics snapshot for RAG context (per the
architecture doc's §4.2 design: "queries Metrics Service for the
correlated time-window's CPU/latency"). Returns None on failure — the
GenAI analysis proceeds with log-only context rather than failing
entirely if Metrics Service happens to be down.
"""

from datetime import datetime, timedelta, timezone

import httpx

from platform_common.logging import get_logger

logger = get_logger(__name__)


class MetricsClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str, *, timeout: float):
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def get_recent_average(
        self, *, service_id: str, metric_name: str, authorization: str, lookback_minutes: int = 30
    ) -> float | None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
        try:
            resp = await self._client.get(
                f"{self._base_url}/api/v1/metrics/query",
                headers={"Authorization": authorization},
                params={
                    "service_id": service_id,
                    "metric_name": metric_name,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "aggregation": "avg",
                    "interval_seconds": lookback_minutes * 60,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            points = resp.json().get("points", [])
            return points[-1]["value"] if points else None
        except Exception as exc:
            logger.warning("failed to fetch correlated metrics", extra={"error": str(exc)})
            return None
