from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class CloudStorageServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "cloud-storage-service"

    JWT_PUBLIC_KEY: str | None = Field(default=None)
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None)

    S3_BUCKET: str = Field(default="platform-storage")
    # None => real AWS S3. Set to MinIO's endpoint (see infra/docker-compose.yml)
    # for local dev / self-hosted deployment.
    S3_ENDPOINT_URL: str | None = Field(default="http://localhost:9000")
    S3_ACCESS_KEY: str = Field(default="platform")
    S3_SECRET_KEY: str = Field(default="platform_local_dev_only")
    S3_REGION: str = Field(default="us-east-1")

    MAX_UPLOAD_SIZE_BYTES: int = Field(default=50 * 1024 * 1024, description="50MB default cap on direct uploads")
    PRESIGNED_URL_EXPIRY_SECONDS: int = Field(default=3600)

    @model_validator(mode="after")
    def _resolve_jwt_key(self) -> "CloudStorageServiceSettings":
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_PATH must be set")
        return self
