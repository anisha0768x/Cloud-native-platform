"""
Test fixtures.

WHY test against real Postgres instead of SQLite: our models use
Postgres-specific types (UUID, and Metrics/other services will use JSONB)
that SQLite either fakes or rejects — a green SQLite test suite gives false
confidence. Each test runs inside a transaction that's rolled back at
teardown, so tests stay fast and don't leak state into each other despite
sharing one real database.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthServiceSettings
from app.core.dependencies import get_db_session
from app.main import create_app


@pytest_asyncio.fixture
async def settings() -> AuthServiceSettings:
    return AuthServiceSettings(DATABASE_URL="postgresql+asyncpg://platform:platform_local_dev_only@localhost:5432/auth_service_test")


@pytest_asyncio.fixture
async def db_session(settings):
    """
    One connection + one outer transaction per test, rolled back at the
    end — the standard pattern for fast, isolated integration tests
    against a real database.
    """
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
    app = create_app()
    app.state.settings = settings

    async def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
