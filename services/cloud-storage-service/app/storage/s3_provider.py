import asyncio
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from platform_common.exceptions import NotFoundError
from platform_common.logging import get_logger

from app.storage.base import StoredObjectInfo

logger = get_logger(__name__)


class S3StorageProvider:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,  # None => real AWS S3; set => MinIO/other S3-compatible endpoint
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def ensure_bucket_exists(self) -> None:
        def _ensure():
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except ClientError:
                self._client.create_bucket(Bucket=self._bucket)

        await asyncio.to_thread(_ensure)

    async def upload(self, *, key: str, data: bytes, content_type: str | None = None) -> StoredObjectInfo:
        def _upload():
            extra_args = {"ContentType": content_type} if content_type else {}
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra_args)

        await asyncio.to_thread(_upload)
        return StoredObjectInfo(
            key=key, size_bytes=len(data), last_modified=datetime.now(timezone.utc), content_type=content_type
        )

    async def download(self, *, key: str) -> bytes:
        def _download() -> bytes:
            try:
                resp = self._client.get_object(Bucket=self._bucket, Key=key)
                return resp["Body"].read()
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise NotFoundError(f"Object '{key}' not found") from exc
                raise

        return await asyncio.to_thread(_download)

    async def delete(self, *, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def list_objects(self, *, prefix: str = "", limit: int = 100) -> list[StoredObjectInfo]:
        def _list():
            resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=limit)
            return resp.get("Contents", [])

        contents = await asyncio.to_thread(_list)
        return [
            StoredObjectInfo(key=obj["Key"], size_bytes=obj["Size"], last_modified=obj["LastModified"])
            for obj in contents
        ]

    async def exists(self, *, key: str) -> bool:
        def _exists() -> bool:
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError:
                return False

        return await asyncio.to_thread(_exists)

    async def generate_presigned_url(self, *, key: str, expires_in_seconds: int = 3600) -> str:
        def _generate() -> str:
            return self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_in_seconds
            )

        return await asyncio.to_thread(_generate)
