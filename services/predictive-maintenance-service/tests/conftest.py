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

from app.core.config import PredictiveMaintenanceServiceSettings
from app.core.dependencies import get_db_session
from app.main import create_app
from app.services.maintenance_service import MaintenanceService

MOCK_METRICS_PORT = 18601
MOCK_K8S_PORT = 18602

_cpu_level = "low"  # "low" | "high" — controls the mock Metrics Service's response


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

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if metric_name == "cpu_usage":
            base = 90.0 if _cpu_level == "high" else 30.0
        else:
            base = 50.0

        points = [
            {"bucket_start": (now - timedelta(hours=5 - i)).isoformat(), "value": base + i}
            for i in range(6)
        ]
        return {
            "service_id": service_id, "metric_name": metric_name, "aggregation": aggregation,
            "interval_seconds": interval_seconds, "points": points,
        }

    return mock


def _build_mock_k8s() -> FastAPI:
    mock = FastAPI()

    @mock.get("/api/v1/k8s/pods")
    async def pods():
        return [
            {"name": "checkout-api-abc", "service_name": "checkout-api", "restart_count": 2},
            {"name": "checkout-api-def", "service_name": "checkout-api", "restart_count": 1},
            {"name": "other-service-xyz", "service_name": "other-service", "restart_count": 9},
        ]

    return mock


def _run_server(app: FastAPI, port: int, health_path: str):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            sync_httpx.get(f"http://127.0.0.1:{port}{health_path}", timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
    return server


@pytest.fixture(scope="session")
def mock_backends():
    metrics_server = _run_server(_build_mock_metrics(), MOCK_METRICS_PORT, "/api/v1/k8s/pods")
    k8s_server = _run_server(_build_mock_k8s(), MOCK_K8S_PORT, "/api/v1/k8s/pods")
    yield {"metrics_url": f"http://127.0.0.1:{MOCK_METRICS_PORT}", "k8s_url": f"http://127.0.0.1:{MOCK_K8S_PORT}"}
    metrics_server.should_exit = True
    k8s_server.should_exit = True


@pytest.fixture(autouse=True)
def reset_state():
    global _cpu_level
    _cpu_level = "low"
    MaintenanceService.clear_model_cache()
    yield
    _cpu_level = "low"
    MaintenanceService.clear_model_cache()


def set_cpu_level(level: str):
    global _cpu_level
    _cpu_level = level


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
async def settings(mock_backends, rsa_keypair):
    _, public_key = rsa_keypair
    return PredictiveMaintenanceServiceSettings(
        DATABASE_URL="postgresql+asyncpg://platform:platform_local_dev_only@localhost:5432/predictive_maintenance_service_test",
        JWT_PUBLIC_KEY=public_key,
        METRICS_SERVICE_URL=mock_backends["metrics_url"],
        K8S_MANAGEMENT_SERVICE_URL=mock_backends["k8s_url"],
        TRAINING_SAMPLE_COUNT=500,  # smaller for fast tests
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
