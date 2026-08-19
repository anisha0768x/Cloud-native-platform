"""
NotificationChannel: each delivery mechanism (webhook, Slack, email)
implements the same tiny interface, so NotificationDispatcher (see
services/dispatcher.py) doesn't need to know which channels are
configured — it just iterates whatever channel list it was given.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class NotificationPayload:
    service_id: str
    severity: str
    message: str
    alert_id: str | None = None


@dataclass
class DeliveryResult:
    channel: str
    success: bool
    error: str | None = None


class NotificationChannel(Protocol):
    name: str

    async def send(self, payload: NotificationPayload) -> DeliveryResult: ...
