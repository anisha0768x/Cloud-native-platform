from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class MonitoringServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "monitoring-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    # Consecutive failed heartbeats before a service is marked `down` and
    # an alert is auto-created. 1 would be too noisy (a single dropped
    # heartbeat during a deploy shouldn't page anyone); this is a
    # deliberately simple fixed threshold — a smarter anomaly-based
    # detector is exactly what the Predictive Maintenance Service (a later
    # module) exists to add on top of this.
    CONSECUTIVE_FAILURES_BEFORE_DOWN: int = Field(default=3)

    # How many recent health checks health-summary considers for uptime %.
    HEALTH_SUMMARY_WINDOW_SIZE: int = Field(default=100)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "MonitoringServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
