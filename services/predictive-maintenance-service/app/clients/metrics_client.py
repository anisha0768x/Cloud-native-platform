"""
Fetches recent CPU/memory series from Metrics Service, used to compute
the live trend features (mean/std/slope) the model runs inference on.
Returns None on failure — same graceful-degradation contract used
throughout the platform (Dashboard Service, Traffic Prediction Service).
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

    async def get_recent_series(
        self, *, service_id: str, metric_name: str, authorization: str, lookback_hours: int
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
                    "aggregation": "avg",
                    "interval_seconds": 3600,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            points = resp.json().get("points", [])
            if not points:
                return None
            return [(datetime.fromisoformat(p["bucket_start"]), float(p["value"])) for p in points]
        except Exception as exc:
            logger.warning("failed to fetch metrics series", extra={"metric": metric_name, "error": str(exc)})
            return None
