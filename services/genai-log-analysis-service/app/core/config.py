from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class GenAiLogAnalysisServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "genai-log-analysis-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # "memory" (default): no external dependency, fine for local dev/demo.
    # "opensearch": real deployment, matches infra/docker-compose.yml.
    LOG_STORE_MODE: Literal["memory", "opensearch"] = Field(default="memory")
    OPENSEARCH_HOSTS: list[str] = Field(default_factory=lambda: ["http://localhost:9200"])

    METRICS_SERVICE_URL: str = Field(default="http://localhost:8003")
    BACKEND_CALL_TIMEOUT_SECONDS: float = Field(default=5.0)

    ANTHROPIC_API_KEY: str | None = Field(default=None)
    ANTHROPIC_MODEL: str = Field(default="claude-sonnet-4-6")
    ANTHROPIC_API_URL: str = Field(default="https://api.anthropic.com/v1/messages")
    LLM_TIMEOUT_SECONDS: float = Field(default=8.0)

    # De-dupe identical alert fingerprints within this window rather than
    # re-calling the LLM (and re-scanning logs) for the same underlying
    # issue on every repeated failure — matches the architecture doc's
    # §4.2 cost-control design.
    ANALYSIS_CACHE_TTL_SECONDS: int = Field(default=600)

    RECENT_ERROR_LOG_LIMIT: int = Field(default=20)

    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:9092")
    LOGS_TOPIC: str = Field(default="logs.raw")
    KAFKA_CONSUMER_GROUP: str = Field(default="genai-log-analysis-service")
    ENABLE_KAFKA_CONSUMER: bool = Field(default=True)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "GenAiLogAnalysisServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
