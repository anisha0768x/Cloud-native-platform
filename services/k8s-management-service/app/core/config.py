from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class K8sManagementServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "k8s-management-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN")

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    # "demo": synthetic-but-consistent cluster state, no cluster required.
    # "kubernetes": real cluster via the official client (in-cluster
    # ServiceAccount config, or local kubeconfig for dev against a real
    # cluster). Defaults to demo so the platform is usable out of the box.
    CLUSTER_MODE: Literal["demo", "kubernetes"] = Field(default="demo")

    SNAPSHOT_INTERVAL_SECONDS: int = Field(
        default=30, description="How often the background job captures a cluster_snapshots row"
    )
    ENABLE_SNAPSHOT_WORKER: bool = Field(default=True)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "K8sManagementServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
