from platform_common.exceptions import NotFoundError

from app.channels.base import NotificationPayload
from app.repositories.notification_repository import NotificationRepository
from app.services.dispatcher import NotificationDispatcher


class NotificationService:
    def __init__(self, dispatcher: NotificationDispatcher, repo: NotificationRepository):
        self._dispatcher = dispatcher
        self._repo = repo

    async def send(self, *, service_id: str, severity: str, message: str, alert_id: str | None) -> dict:
        notification = await self._repo.create(
            alert_id=alert_id, service_id=service_id, severity=severity, message=message
        )

        payload = NotificationPayload(service_id=service_id, severity=severity, message=message, alert_id=alert_id)
        results = await self._dispatcher.dispatch(payload)

        for result in results:
            await self._repo.add_delivery_attempt(
                notification_id=notification.id, channel=result.channel, success=result.success, error=result.error
            )

        # Re-fetch so the response includes the delivery_attempts we just added.
        refreshed = await self._repo.get_by_id(notification.id)
        return refreshed

    async def acknowledge(self, notification_id):
        notification = await self._repo.get_by_id(notification_id)
        if notification is None:
            raise NotFoundError(f"Notification '{notification_id}' not found")
        return await self._repo.acknowledge(notification)

    async def history(self, *, service_id: str | None = None, status: str | None = None, limit: int = 100):
        return await self._repo.history(service_id=service_id, status=status, limit=limit)
