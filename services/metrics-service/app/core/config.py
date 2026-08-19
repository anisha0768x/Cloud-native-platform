from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class MetricsServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "metrics-service"

    DATABASE_URL: str = Field(..., description="Postgres/TimescaleDB async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:9092")
    METRICS_TOPIC: str = Field(default="metrics.raw")
    KAFKA_CONSUMER_GROUP: str = Field(default="metrics-service")

    # Whether to actually start the Kafka consumer background task on
    # startup. Tests set this False so they don't need a live Kafka broker
    # just to exercise the REST/query surface — the consumer's own logic
    # is tested separately, directly, against a real broker.
    ENABLE_KAFKA_CONSUMER: bool = Field(default=True)

    MAX_QUERY_RANGE_DAYS: int = Field(
        default=90, description="Guardrail: reject queries spanning more than this, to bound query cost"
    )

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "MetricsServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
