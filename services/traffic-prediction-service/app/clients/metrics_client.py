"""
Fetches historical `request_count` series from Metrics Service (Module 5).
Returns None on any failure (network, auth, no data) — same graceful-
degradation contract as the Dashboard Service's BackendClient — so the
caller can fall back to synthetic data rather than fail the whole
prediction request over a transient Metrics Service blip.
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

    async def get_historical_series(
        self, *, service_id: str, authorization: str, lookback_hours: int, metric_name: str = "request_count"
    ) -> list[tuple[datetime, float]] | None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=lookback_hours)
        try:
            resp = await self._client.get(
                f"{self._base_url}/api/v1/metrics/query",
                headers={"Authorization": authorization},
                params={
                    "service_id": service_id,
                    "metric_name": metric_name,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "aggregation": "sum",
                    "interval_seconds": 3600,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            body = resp.json()
            points = body.get("points", [])
            if not points:
                return None
            return [(datetime.fromisoformat(p["bucket_start"]), float(p["value"])) for p in points]
        except Exception as exc:
            logger.warning("failed to fetch historical metrics, will fall back", extra={"error": str(exc)})
            return None
