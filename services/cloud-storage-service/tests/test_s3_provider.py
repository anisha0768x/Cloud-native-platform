import pytest
from moto import mock_aws

from app.storage.s3_provider import S3StorageProvider
from platform_common.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def provider():
    with mock_aws():
        p = S3StorageProvider(
            bucket="test-bucket",
            endpoint_url=None,  # moto intercepts regardless of endpoint_url
            access_key="test",
            secret_key="test",
            region="us-east-1",
        )
        yield p


async def test_ensure_bucket_exists_creates_bucket(provider):
    await provider.ensure_bucket_exists()
    # Calling again must not raise (idempotent).
    await provider.ensure_bucket_exists()


async def test_upload_and_download_roundtrip(provider):
    await provider.ensure_bucket_exists()
    await provider.upload(key="reports/q1.csv", data=b"col1,col2\n1,2\n", content_type="text/csv")

    downloaded = await provider.download(key="reports/q1.csv")
    assert downloaded == b"col1,col2\n1,2\n"


async def test_download_nonexistent_key_raises_not_found(provider):
    await provider.ensure_bucket_exists()
    with pytest.raises(NotFoundError):
        await provider.download(key="does/not/exist.txt")


async def test_exists_reflects_actual_state(provider):
    await provider.ensure_bucket_exists()
    assert await provider.exists(key="foo.txt") is False
    await provider.upload(key="foo.txt", data=b"hi")
    assert await provider.exists(key="foo.txt") is True


async def test_delete_removes_object(provider):
    await provider.ensure_bucket_exists()
    await provider.upload(key="temp.txt", data=b"delete me")
    assert await provider.exists(key="temp.txt") is True

    await provider.delete(key="temp.txt")
    assert await provider.exists(key="temp.txt") is False


async def test_list_objects_filters_by_prefix(provider):
    await provider.ensure_bucket_exists()
    await provider.upload(key="logs/2026-01-01/a.log", data=b"a")
    await provider.upload(key="logs/2026-01-02/b.log", data=b"b")
    await provider.upload(key="reports/q1.csv", data=b"c")

    logs = await provider.list_objects(prefix="logs/")
    assert len(logs) == 2
    assert all(obj.key.startswith("logs/") for obj in logs)

    reports = await provider.list_objects(prefix="reports/")
    assert len(reports) == 1


async def test_upload_returns_correct_size(provider):
    await provider.ensure_bucket_exists()
    info = await provider.upload(key="sized.txt", data=b"12345")
    assert info.size_bytes == 5


async def test_presigned_url_is_generated(provider):
    await provider.ensure_bucket_exists()
    await provider.upload(key="shared.txt", data=b"hello")
    url = await provider.generate_presigned_url(key="shared.txt", expires_in_seconds=60)
    assert "shared.txt" in url
    assert url.startswith("http")
