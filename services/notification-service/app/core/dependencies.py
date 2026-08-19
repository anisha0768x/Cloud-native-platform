from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import NotificationChannel
from app.channels.email_channel import EmailChannel
from app.channels.slack import SlackChannel
from app.channels.webhook import WebhookChannel
from app.core.config import NotificationServiceSettings
from app.repositories.notification_repository import NotificationRepository
from app.services.dispatcher import NotificationDispatcher
from app.services.notification_service import NotificationService


def get_settings(request: Request) -> NotificationServiceSettings:
    return request.app.state.settings


async def get_db_session(request: Request) -> AsyncSession:
    async with request.app.state.db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def build_channels(settings: NotificationServiceSettings, http_client) -> list[NotificationChannel]:
    """
    Only channels with the required config present are included — this is
    what lets the service run with zero channels configured (every send
    just records zero delivery attempts) without erroring, matching the
    platform's "optional, gracefully absent" pattern for external
    integrations rather than requiring every channel to be wired up.
    """
    channels: list[NotificationChannel] = []
    if settings.WEBHOOK_URL:
        channels.append(WebhookChannel(http_client, settings.WEBHOOK_URL, timeout=settings.CHANNEL_TIMEOUT_SECONDS))
    if settings.SLACK_WEBHOOK_URL:
        channels.append(SlackChannel(http_client, settings.SLACK_WEBHOOK_URL, timeout=settings.CHANNEL_TIMEOUT_SECONDS))
    if settings.SMTP_HOST and settings.SMTP_TO_ADDRESSES:
        channels.append(
            EmailChannel(
                smtp_host=settings.SMTP_HOST,
                smtp_port=settings.SMTP_PORT,
                from_address=settings.SMTP_FROM_ADDRESS,
                to_addresses=settings.SMTP_TO_ADDRESSES,
                use_tls=settings.SMTP_USE_TLS,
            )
        )
    return channels


def get_notification_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> NotificationService:
    settings: NotificationServiceSettings = request.app.state.settings
    channels = build_channels(settings, request.app.state.http_client)
    dispatcher = NotificationDispatcher(channels)
    return NotificationService(dispatcher, NotificationRepository(session))
