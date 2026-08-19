"""
Fetches pod restart counts from K8s Management Service, matched by
service_name label — restart_count is fundamentally a pod-level concept
(see the master architecture doc's data model), so this is the correct
source rather than duplicating restart tracking in Monitoring Service.
"""

import httpx

from platform_common.logging import get_logger

logger = get_logger(__name__)


class K8sClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str, *, timeout: float):
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def get_total_restart_count(self, *, service_name: str, authorization: str) -> int | None:
        try:
            resp = await self._client.get(
                f"{self._base_url}/api/v1/k8s/pods",
                headers={"Authorization": authorization},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            pods = resp.json()
            matching = [p for p in pods if p.get("service_name") == service_name]
            return sum(p.get("restart_count", 0) for p in matching)
        except Exception as exc:
            logger.warning("failed to fetch pod restart counts", extra={"error": str(exc)})
            return None
