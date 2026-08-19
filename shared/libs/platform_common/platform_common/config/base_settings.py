"""
Base configuration for all services.

WHY a shared BaseServiceSettings instead of each service reading os.environ
directly:
  - 12-factor compliance: every service configures itself purely via env
    vars, which is exactly how K8s injects config (ConfigMaps/Secrets).
  - Fail-fast: Pydantic validates types/required fields at process startup,
    not on the first request that happens to touch a bad value.
  - Consistency: every service ends up with the same field names
    (SERVICE_NAME, LOG_LEVEL, DATABASE_URL, etc.), which matters because
    the Monitoring Service and log pipeline key off these consistently.

Each microservice subclasses BaseServiceSettings and adds its own
service-specific fields (e.g. Auth Service adds JWT_SECRET_KEY).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Identity ---
    SERVICE_NAME: str = Field(..., description="Unique service identifier, e.g. 'auth-service'")
    SERVICE_VERSION: str = Field(default="0.1.0")
    ENVIRONMENT: Literal["local", "dev", "staging", "prod"] = Field(default="local")

    # --- HTTP ---
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    # --- Logging ---
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # --- Datastores (individual services override/extend as needed) ---
    DATABASE_URL: str | None = Field(default=None, description="Async SQLAlchemy DSN")
    REDIS_URL: str | None = Field(default=None)

    # --- Kafka ---
    KAFKA_BOOTSTRAP_SERVERS: str | None = Field(default=None)

    # --- Security ---
    JWT_PUBLIC_KEY: str | None = Field(
        default=None,
        description="Used by every service (except Auth) to VERIFY tokens issued by Auth Service.",
    )
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT == "local"


@lru_cache
def get_settings(settings_cls: type[BaseServiceSettings]) -> BaseServiceSettings:
    """
    Cached settings loader. Each service calls this once with its own
    Settings subclass so env parsing happens a single time per process,
    not on every request.
    """
    return settings_cls()
