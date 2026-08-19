from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class NotificationServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "notification-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    # Every channel below is OPTIONAL — a channel with no URL/host
    # configured is simply skipped by the dispatcher (see
    # services/dispatcher.py) rather than failing the whole notification.
    WEBHOOK_URL: str | None = Field(default=None)
    SLACK_WEBHOOK_URL: str | None = Field(default=None)

    SMTP_HOST: str | None = Field(default=None)
    SMTP_PORT: int = Field(default=25)
    SMTP_FROM_ADDRESS: str = Field(default="alerts@platform.local")
    SMTP_TO_ADDRESSES: list[str] = Field(default_factory=list)
    SMTP_USE_TLS: bool = Field(default=False)

    CHANNEL_TIMEOUT_SECONDS: float = Field(default=5.0)

    # If a notification stays unacknowledged this long, the escalation
    # worker sends it again via the SAME configured channels with an
    # "ESCALATED" marker — a real deployment might route escalations to a
    # different on-call channel/pager, which is a natural next step once
    # this platform has an on-call-rotation concept; not built here.
    ESCALATION_WINDOW_MINUTES: int = Field(default=15)
    ESCALATION_WORKER_POLL_SECONDS: int = Field(default=60)
    ENABLE_ESCALATION_WORKER: bool = Field(default=True)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "NotificationServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
