"""
NotificationDispatcher: sends a payload to every channel it was given,
concurrently, and returns each channel's individual result. WHY it
doesn't raise on a channel failure: a notification going out on 2 of 3
configured channels is a partial success worth recording accurately (see
DeliveryAttempt per channel), not a reason to fail the whole send — the
alert still reached someone.
"""

import asyncio

from app.channels.base import DeliveryResult, NotificationChannel, NotificationPayload


class NotificationDispatcher:
    def __init__(self, channels: list[NotificationChannel]):
        self._channels = channels

    async def dispatch(self, payload: NotificationPayload) -> list[DeliveryResult]:
        if not self._channels:
            return []
        results = await asyncio.gather(*(channel.send(payload) for channel in self._channels))
        return list(results)
