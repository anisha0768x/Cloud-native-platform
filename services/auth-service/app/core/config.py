"""
Auth Service configuration.

Extends the shared BaseServiceSettings with the fields ONLY this service
needs: the RSA keypair (private key to SIGN tokens — held nowhere else on
the platform; public key to verify its own tokens on the /me endpoint) and
token lifetimes.

Keys can be supplied two ways:
  1. Directly as PEM content via JWT_PRIVATE_KEY / JWT_PUBLIC_KEY (simple
     for local `python -m uvicorn` runs with a .env file).
  2. As file paths via JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH — this is
     the path used in Docker/K8s, where a Secret is mounted as a file
     rather than inlined as an env var (avoids multi-line PEM content
     surviving Docker's simpler env_file parser, and matches how K8s
     Secret volume mounts actually work).
"""

from pathlib import Path

from pydantic import Field, model_validator

from platform_common.config import BaseServiceSettings


class AuthServiceSettings(BaseServiceSettings):
    SERVICE_NAME: str = "auth-service"

    DATABASE_URL: str = Field(..., description="Postgres async DSN, e.g. postgresql+asyncpg://...")

    JWT_PRIVATE_KEY: str | None = Field(default=None, description="PEM content, this service only")
    JWT_PUBLIC_KEY: str | None = Field(default=None, description="PEM content, distributed to all services")
    JWT_PRIVATE_KEY_PATH: str | None = Field(default=None, description="Path to mounted private key PEM file")
    JWT_PUBLIC_KEY_PATH: str | None = Field(default=None, description="Path to mounted public key PEM file")

    ACCESS_TOKEN_EXPIRE_SECONDS: int = Field(default=900)  # 15 minutes
    REFRESH_TOKEN_EXPIRE_SECONDS: int = Field(default=604800)  # 7 days

    MAX_FAILED_LOGIN_ATTEMPTS: int = Field(default=5)
    FAILED_LOGIN_LOCKOUT_SECONDS: int = Field(default=900)  # 15 minutes

    @model_validator(mode="after")
    def _resolve_keys_from_paths(self) -> "AuthServiceSettings":
        if self.JWT_PRIVATE_KEY is None and self.JWT_PRIVATE_KEY_PATH:
            self.JWT_PRIVATE_KEY = Path(self.JWT_PRIVATE_KEY_PATH).read_text()
        if self.JWT_PUBLIC_KEY is None and self.JWT_PUBLIC_KEY_PATH:
            self.JWT_PUBLIC_KEY = Path(self.JWT_PUBLIC_KEY_PATH).read_text()
        if not self.JWT_PRIVATE_KEY or not self.JWT_PUBLIC_KEY:
            raise ValueError(
                "JWT keys not configured: set JWT_PRIVATE_KEY/JWT_PUBLIC_KEY directly, "
                "or JWT_PRIVATE_KEY_PATH/JWT_PUBLIC_KEY_PATH to mounted files."
            )
        return self

