"""
StorageProvider: abstracts object storage, same pattern as ClusterProvider
(Module 6) and LogStore (Module 10). One implementation here:
S3StorageProvider, using boto3 (sync client wrapped in asyncio.to_thread —
same reasoning as the Kubernetes client in Module 6: boto3 has no
first-party async client, and adding aioboto3 pulled in a broken
dependency chain in this environment, so wrapping the sync client is both
simpler and more robust here).

Points at a real S3-compatible endpoint — MinIO in local dev (already
provisioned in infra/docker-compose.yml), real AWS S3 in production.
Unlike some earlier modules' "provider" abstractions, this one has ONLY
one real implementation because there's nothing to fall back to that
would be meaningfully different — object storage IS the S3 API pretty
much everywhere (MinIO, AWS S3, GCS's S3-compatibility mode, etc.).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class StoredObjectInfo:
    key: str
    size_bytes: int
    last_modified: datetime
    content_type: str | None = None


class StorageProvider(Protocol):
    async def upload(self, *, key: str, data: bytes, content_type: str | None = None) -> StoredObjectInfo: ...

    async def download(self, *, key: str) -> bytes: ...

    async def delete(self, *, key: str) -> None: ...

    async def list_objects(self, *, prefix: str = "", limit: int = 100) -> list[StoredObjectInfo]: ...

    async def exists(self, *, key: str) -> bool: ...

    async def generate_presigned_url(self, *, key: str, expires_in_seconds: int = 3600) -> str: ...
