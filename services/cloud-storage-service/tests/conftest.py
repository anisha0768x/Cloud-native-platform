import uuid

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

from platform_common.security import encode_token

from app.core.config import CloudStorageServiceSettings
from app.main import create_app
from app.storage.s3_provider import S3StorageProvider


@pytest.fixture(scope="session")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def make_token(rsa_keypair, *, permissions: list[str]) -> str:
    private_key, _ = rsa_keypair
    return encode_token(
        private_key=private_key, subject=str(uuid.uuid4()), roles=["operator"],
        permissions=permissions, expires_in_seconds=3600,
    )


@pytest_asyncio.fixture
async def client(rsa_keypair):
    _, public_key = rsa_keypair
    settings = CloudStorageServiceSettings(
        JWT_PUBLIC_KEY=public_key,
        S3_BUCKET="test-platform-storage",
        S3_ENDPOINT_URL=None,
        S3_ACCESS_KEY="test",
        S3_SECRET_KEY="test",
        MAX_UPLOAD_SIZE_BYTES=1024,  # small, so the size-limit test doesn't need a huge payload
    )

    with mock_aws():
        app = create_app()
        app.state.settings = settings
        app.state.storage_provider = S3StorageProvider(
            bucket=settings.S3_BUCKET,
            endpoint_url=settings.S3_ENDPOINT_URL,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
            region=settings.S3_REGION,
        )
        await app.state.storage_provider.ensure_bucket_exists()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
