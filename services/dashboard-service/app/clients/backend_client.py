"""
BackendClient: wraps a call to another platform service.

WHY it returns None on failure instead of raising: this is the mechanism
that makes graceful degradation possible. If Metrics Service is briefly
down, the Executive Dashboard should still render with whatever data
Monitoring and K8s Management successfully returned, flagging the gap in
`partial_errors` — not throw a 500 and show the operator a blank page
right when something is already going wrong elsewhere in the platform.
The caller (DashboardService) is responsible for deciding what a `None`
means for that specific field (usually: omit it, or default to empty).
"""

from platform_common.logging import get_logger

logger = get_logger(__name__)


class BackendClient:
    def __init__(self, http_client, base_url: str, *, timeout: float):
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def get(self, path: str, *, authorization: str, params: dict | None = None) -> dict | list | None:
        try:
            resp = await self._client.get(
                f"{self._base_url}{path}",
                headers={"Authorization": authorization},
                params=params or {},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "backend call failed, degrading gracefully",
                extra={"url": f"{self._base_url}{path}", "error": str(exc)},
            )
            return None
