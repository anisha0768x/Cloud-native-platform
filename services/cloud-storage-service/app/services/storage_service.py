"""
Thin validation layer over StorageProvider — deliberately not just a
pass-through, since object keys coming from API requests need the same
scrutiny any file-path-like user input needs.
"""

from platform_common.exceptions import ValidationError

from app.storage.base import StorageProvider, StoredObjectInfo


def validate_key(key: str) -> None:
    """
    Rejects path-traversal attempts and other malformed keys BEFORE they
    reach the storage backend — S3-compatible stores generally treat keys
    as flat strings (no real directory traversal risk server-side), but a
    key like `../../other-tenant/secrets.txt` is still worth rejecting
    outright rather than trusting it's harmless just because S3 tolerates it.
    """
    if not key or key.strip() != key:
        raise ValidationError("Object key must not be empty or have leading/trailing whitespace")
    if ".." in key:
        raise ValidationError("Object key must not contain '..'")
    if key.startswith("/"):
        raise ValidationError("Object key must not start with '/'")
    if len(key) > 1024:
        raise ValidationError("Object key must not exceed 1024 characters")


class CloudStorageService:
    def __init__(self, provider: StorageProvider, *, max_upload_size_bytes: int):
        self._provider = provider
        self._max_size = max_upload_size_bytes

    async def upload(self, *, key: str, data: bytes, content_type: str | None = None) -> StoredObjectInfo:
        validate_key(key)
        if len(data) > self._max_size:
            raise ValidationError(
                f"Upload exceeds maximum size of {self._max_size} bytes",
                details={"uploaded_bytes": len(data), "max_bytes": self._max_size},
            )
        return await self._provider.upload(key=key, data=data, content_type=content_type)

    async def download(self, *, key: str) -> bytes:
        validate_key(key)
        return await self._provider.download(key=key)

    async def delete(self, *, key: str) -> None:
        validate_key(key)
        await self._provider.delete(key=key)

    async def list_objects(self, *, prefix: str = "", limit: int = 100) -> list[StoredObjectInfo]:
        return await self._provider.list_objects(prefix=prefix, limit=limit)

    async def exists(self, *, key: str) -> bool:
        validate_key(key)
        return await self._provider.exists(key=key)

    async def presigned_url(self, *, key: str, expires_in_seconds: int) -> str:
        validate_key(key)
        return await self._provider.generate_presigned_url(key=key, expires_in_seconds=expires_in_seconds)
