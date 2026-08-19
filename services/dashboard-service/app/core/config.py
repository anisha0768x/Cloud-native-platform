from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class DashboardServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "dashboard-service"

    # No DATABASE_URL — this service is a stateless aggregator, its only
    # storage is the Redis cache (REDIS_URL, inherited from BaseServiceSettings).
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    MONITORING_SERVICE_URL: str = Field(default="http://localhost:8002")
    K8S_MANAGEMENT_SERVICE_URL: str = Field(default="http://localhost:8004")

    # Short TTL by design: dashboards should feel near-real-time, but
    # every page refresh/poll hitting 3 backend services directly would
    # multiply load unnecessarily. 15s is a deliberate middle ground —
    # tune per-dashboard later if some need to be fresher than others.
    CACHE_TTL_SECONDS: int = Field(default=15)

    BACKEND_CALL_TIMEOUT_SECONDS: float = Field(default=5.0)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "DashboardServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
