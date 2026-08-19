from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class PredictiveMaintenanceServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "predictive-maintenance-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    METRICS_SERVICE_URL: str = Field(default="http://localhost:8003")
    K8S_MANAGEMENT_SERVICE_URL: str = Field(default="http://localhost:8004")
    BACKEND_CALL_TIMEOUT_SECONDS: float = Field(default=5.0)

    FEATURE_LOOKBACK_HOURS: int = Field(default=6, description="Window for computing mean/std/slope trend features")

    TRAINING_SAMPLE_COUNT: int = Field(default=2000)
    MODEL_CACHE_TTL_SECONDS: int = Field(default=3600)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "PredictiveMaintenanceServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
