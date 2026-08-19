import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.security import encode_token

from app.core.config import K8sManagementServiceSettings
from app.core.dependencies import get_db_session
from app.main import create_app


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


def make_token(rsa_keypair, *, permissions: list[str], subject: str = "test-user") -> str:
    private_key, _ = rsa_keypair
    return encode_token(
        private_key=private_key,
        subject=subject,
        roles=["operator"],
        permissions=permissions,
        expires_in_seconds=3600,
    )


@pytest_asyncio.fixture
async def settings(rsa_keypair):
    _, public_key = rsa_keypair
    return K8sManagementServiceSettings(
        DATABASE_URL="postgresql+asyncpg://platform:platform_local_dev_only@localhost:5432/k8s_management_service_test",
        JWT_PUBLIC_KEY=public_key,
        CLUSTER_MODE="demo",
        ENABLE_SNAPSHOT_WORKER=False,  # HTTP tests drive snapshots explicitly where needed
    )


@pytest_asyncio.fixture
async def db_session(settings):
    from platform_common.db import Database

    db = Database(settings.DATABASE_URL)
    async with db.engine.connect() as connection:
        trans = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await db.dispose()


@pytest_asyncio.fixture
async def client(settings, db_session):
    from app.providers import build_cluster_provider

    app = create_app()
    app.state.settings = settings
    app.state.cluster_provider = build_cluster_provider(settings.CLUSTER_MODE)

    async def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
