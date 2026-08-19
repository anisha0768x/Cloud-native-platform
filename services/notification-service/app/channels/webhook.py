import httpx

from app.channels.base import DeliveryResult, NotificationPayload
from platform_common.logging import get_logger

logger = get_logger(__name__)


class WebhookChannel:
    name = "webhook"

    def __init__(self, http_client: httpx.AsyncClient, url: str, *, timeout: float):
        self._client = http_client
        self._url = url
        self._timeout = timeout

    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        try:
            resp = await self._client.post(
                self._url,
                json={
                    "alert_id": payload.alert_id,
                    "service_id": payload.service_id,
                    "severity": payload.severity,
                    "message": payload.message,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return DeliveryResult(channel=self.name, success=True)
        except Exception as exc:
            logger.warning("webhook delivery failed", extra={"error": str(exc)})
            return DeliveryResult(channel=self.name, success=False, error=str(exc))
