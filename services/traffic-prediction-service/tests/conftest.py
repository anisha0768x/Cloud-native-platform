import asyncio
import threading
import time
import uuid

import httpx as sync_httpx
import pytest
import pytest_asyncio
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.security import encode_token

from app.core.config import TrafficPredictionServiceSettings
from app.core.dependencies import get_db_session
from app.main import create_app
from app.services.prediction_service import PredictionService

MOCK_METRICS_PORT = 18501

# Module-level flag: whether the mock Metrics Service should report
# "enough real historical data" or "not enough" (forcing synthetic fallback).
_metrics_has_sufficient_data = True


def _build_mock_metrics() -> FastAPI:
    mock = FastAPI()

    @mock.get("/api/v1/metrics/query")
    async def query(
        service_id: str = Query(...),
        metric_name: str = Query(...),
        start: str = Query(...),
        end: str = Query(...),
        aggregation: str = Query(...),
        interval_seconds: int = Query(...),
    ):
        from datetime import datetime, timedelta, timezone

        if not _metrics_has_sufficient_data:
            return {"service_id": service_id, "metric_name": metric_name, "aggregation": aggregation, "interval_seconds": interval_seconds, "points": []}

        # Real-looking hourly series with a clear daily pattern, so tests
        # can assert the model actually used THIS (not the synthetic
        # fallback) when data_source == "historical".
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        points = []
        for i in range(24 * 21):
            ts = now - timedelta(hours=24 * 21 - i)
            hour_factor = 1.0 if 8 <= ts.hour <= 20 else 0.2
            points.append({"bucket_start": ts.isoformat(), "value": 1000.0 * hour_factor})

        return {
            "service_id": service_id,
            "metric_name": metric_name,
            "aggregation": aggregation,
            "interval_seconds": interval_seconds,
            "points": points,
        }

    return mock


@pytest.fixture(scope="session")
def mock_metrics_server():
    config = uvicorn.Config(_build_mock_metrics(), host="127.0.0.1", port=MOCK_METRICS_PORT, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            sync_httpx.get(
                f"http://127.0.0.1:{MOCK_METRICS_PORT}/api/v1/metrics/query",
                params={
                    "service_id": "x", "metric_name": "x", "start": "2024-01-01T00:00:00Z",
                    "end": "2024-01-01T01:00:00Z", "aggregation": "sum", "interval_seconds": 3600,
                },
                timeout=0.3,
            )
            break
        except Exception:
            time.sleep(0.1)

    yield f"http://127.0.0.1:{MOCK_METRICS_PORT}"
    server.should_exit = True


@pytest.fixture(autouse=True)
def reset_metrics_data_flag_and_model_cache():
    global _metrics_has_sufficient_data
    _metrics_has_sufficient_data = True
    PredictionService.clear_model_cache()
    yield
    _metrics_has_sufficient_data = True
    PredictionService.clear_model_cache()


def set_metrics_has_data(value: bool):
    global _metrics_has_sufficient_data
    _metrics_has_sufficient_data = value


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
        private_key=private_key,
        subject=str(uuid.uuid4()),
        roles=["operator"],
        permissions=permissions,
        expires_in_seconds=3600,
    )


@pytest_asyncio.fixture
async def settings(mock_metrics_server, rsa_keypair):
    _, public_key = rsa_keypair
    return TrafficPredictionServiceSettings(
        DATABASE_URL="postgresql+asyncpg://platform:platform_local_dev_only@localhost:5432/traffic_prediction_service_test",
        JWT_PUBLIC_KEY=public_key,
        METRICS_SERVICE_URL=mock_metrics_server,
        LOOKBACK_HOURS=24 * 21,
        MIN_TRAINING_POINTS=48,
        REQUESTS_PER_POD_CAPACITY=200,
        MODEL_CACHE_TTL_SECONDS=3600,
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
    import httpx

    app = create_app()
    app.state.settings = settings
    app.state.http_client = httpx.AsyncClient()

    async def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.http_client.aclose()
