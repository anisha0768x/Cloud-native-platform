"""
API Gateway configuration.

The ROUTE_TABLE is the heart of this service: a mapping of path prefix ->
upstream base URL. It's expressed as data (not a series of if/elif) so
adding the next service (Module 4 onward) is a one-line config change,
not a code change to the gateway itself.

PUBLIC_PATHS lists endpoints that must be reachable WITHOUT a valid JWT
(registration, login, refresh, health checks, docs) — everything else
requires a syntactically valid, unexpired token before the gateway will
forward it.
"""

from pydantic import Field

from platform_common.config import BaseServiceSettings


class RouteEntry:
    __slots__ = ("prefix", "upstream_base_url")

    def __init__(self, prefix: str, upstream_base_url: str):
        self.prefix = prefix
        self.upstream_base_url = upstream_base_url.rstrip("/")


class GatewaySettings(BaseServiceSettings):
    SERVICE_NAME: str = "api-gateway"

    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    AUTH_SERVICE_URL: str = Field(default="http://localhost:8001")
    MONITORING_SERVICE_URL: str = Field(default="http://localhost:8002")
    METRICS_SERVICE_URL: str = Field(default="http://localhost:8003")
    K8S_MANAGEMENT_SERVICE_URL: str = Field(default="http://localhost:8004")
    DASHBOARD_SERVICE_URL: str = Field(default="http://localhost:8005")
    TRAFFIC_PREDICTION_SERVICE_URL: str = Field(default="http://localhost:8006")
    PREDICTIVE_MAINTENANCE_SERVICE_URL: str = Field(default="http://localhost:8007")
    GENAI_LOG_ANALYSIS_SERVICE_URL: str = Field(default="http://localhost:8008")
    NOTIFICATION_SERVICE_URL: str = Field(default="http://localhost:8009")
    CLOUD_STORAGE_SERVICE_URL: str = Field(default="http://localhost:8010")

    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Max requests per window per client")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)

    UPSTREAM_TIMEOUT_SECONDS: float = Field(default=10.0)

    def model_post_init(self, __context) -> None:
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            from pathlib import Path

            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()

    @property
    def route_table(self) -> list[RouteEntry]:
        """
        Ordered list — first matching prefix wins, so more specific
        prefixes must be listed before more general ones. As each new
        service module is built, its route is added here.
        """
        return [
            RouteEntry("/api/v1/auth", self.AUTH_SERVICE_URL),
            RouteEntry("/api/v1/services", self.MONITORING_SERVICE_URL),
            RouteEntry("/api/v1/alerts", self.MONITORING_SERVICE_URL),
            RouteEntry("/api/v1/metrics", self.METRICS_SERVICE_URL),
            RouteEntry("/api/v1/k8s", self.K8S_MANAGEMENT_SERVICE_URL),
            RouteEntry("/api/v1/dashboards", self.DASHBOARD_SERVICE_URL),
            RouteEntry("/api/v1/predictions/traffic", self.TRAFFIC_PREDICTION_SERVICE_URL),
            RouteEntry("/api/v1/predictions/maintenance", self.PREDICTIVE_MAINTENANCE_SERVICE_URL),
            RouteEntry("/api/v1/logs", self.GENAI_LOG_ANALYSIS_SERVICE_URL),
            RouteEntry("/api/v1/genai", self.GENAI_LOG_ANALYSIS_SERVICE_URL),
            RouteEntry("/api/v1/notifications", self.NOTIFICATION_SERVICE_URL),
            RouteEntry("/api/v1/storage", self.CLOUD_STORAGE_SERVICE_URL),
            # All 12 backend services from the architecture doc are now routed.
        ]

    # Paths reachable without a valid JWT.
    PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
