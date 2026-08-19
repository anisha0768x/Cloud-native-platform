import uuid

from fastapi import APIRouter, Depends, Query

from platform_common.security import TokenPayload, require_permission

from app.core.dependencies import get_notification_service
from app.schemas.notification import NotificationResponse, SendNotificationRequest
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.post("", response_model=NotificationResponse, status_code=201)
async def send_notification(
    body: SendNotificationRequest,
    notifications: NotificationService = Depends(get_notification_service),
    _: TokenPayload = Depends(require_permission("notifications:send")),
):
    return await notifications.send(
        service_id=body.service_id, severity=body.severity, message=body.message, alert_id=body.alert_id
    )


@router.post("/{notification_id}/acknowledge", response_model=NotificationResponse)
async def acknowledge_notification(
    notification_id: uuid.UUID,
    notifications: NotificationService = Depends(get_notification_service),
    _: TokenPayload = Depends(require_permission("alert:acknowledge")),
):
    return await notifications.acknowledge(notification_id)


@router.get("", response_model=list[NotificationResponse])
async def notification_history(
    service_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    notifications: NotificationService = Depends(get_notification_service),
    _: TokenPayload = Depends(require_permission("alert:read")),
):
    return await notifications.history(service_id=service_id, status=status_filter, limit=limit)
