from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class TrafficPredictionServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "traffic-prediction-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    METRICS_SERVICE_URL: str = Field(default="http://localhost:8003")
    BACKEND_CALL_TIMEOUT_SECONDS: float = Field(default=5.0)

    LOOKBACK_HOURS: int = Field(default=24 * 21, description="How much history to train on (21 days)")
    MIN_TRAINING_POINTS: int = Field(
        default=48, description="Below this many real data points, fall back to synthetic training data"
    )

    # Scaling recommendation: how many concurrent requests one pod is
    # assumed to handle comfortably. A real deployment would derive this
    # per-service from observed capacity rather than one global constant
    # — noted as a concrete improvement, kept simple here since per-service
    # capacity profiling is its own scope.
    REQUESTS_PER_POD_CAPACITY: int = Field(default=200)

    MODEL_CACHE_TTL_SECONDS: int = Field(
        default=3600, description="Retrain a service's model after this long, even if still cached"
    )

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "TrafficPredictionServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
