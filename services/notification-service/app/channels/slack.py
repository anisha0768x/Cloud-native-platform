import httpx

from app.channels.base import DeliveryResult, NotificationPayload
from platform_common.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


class SlackChannel:
    """
    Distinct from WebhookChannel despite both being HTTP POSTs: Slack's
    Incoming Webhook API expects a specific JSON shape (`{"text": ...}`,
    optionally with `blocks` for richer formatting) — reusing the generic
    webhook's raw-JSON payload would just show up as a broken message in
    Slack, not a webhook failure, so this is worth its own small class
    rather than a formatting branch inside WebhookChannel.
    """

    name = "slack"

    def __init__(self, http_client: httpx.AsyncClient, webhook_url: str, *, timeout: float):
        self._client = http_client
        self._webhook_url = webhook_url
        self._timeout = timeout

    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        emoji = _SEVERITY_EMOJI.get(payload.severity.lower(), "⚪")
        text = f"{emoji} *[{payload.severity.upper()}]* `{payload.service_id}`: {payload.message}"
        try:
            resp = await self._client.post(self._webhook_url, json={"text": text}, timeout=self._timeout)
            resp.raise_for_status()
            return DeliveryResult(channel=self.name, success=True)
        except Exception as exc:
            logger.warning("slack delivery failed", extra={"error": str(exc)})
            return DeliveryResult(channel=self.name, success=False, error=str(exc))
