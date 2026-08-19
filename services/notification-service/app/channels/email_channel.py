from email.message import EmailMessage

import aiosmtplib

from app.channels.base import DeliveryResult, NotificationPayload
from platform_common.logging import get_logger

logger = get_logger(__name__)


class EmailChannel:
    name = "email"

    def __init__(self, *, smtp_host: str, smtp_port: int, from_address: str, to_addresses: list[str], use_tls: bool = False):
        self._host = smtp_host
        self._port = smtp_port
        self._from = from_address
        self._to = to_addresses
        self._use_tls = use_tls

    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = ", ".join(self._to)
        message["Subject"] = f"[{payload.severity.upper()}] Alert on {payload.service_id}"
        message.set_content(
            f"Service: {payload.service_id}\n"
            f"Severity: {payload.severity}\n"
            f"Alert ID: {payload.alert_id or 'N/A'}\n\n"
            f"{payload.message}"
        )

        try:
            await aiosmtplib.send(
                message, hostname=self._host, port=self._port, use_tls=self._use_tls, timeout=10
            )
            return DeliveryResult(channel=self.name, success=True)
        except Exception as exc:
            logger.warning("email delivery failed", extra={"error": str(exc)})
            return DeliveryResult(channel=self.name, success=False, error=str(exc))
