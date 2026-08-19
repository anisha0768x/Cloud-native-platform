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
from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.security import encode_token

from app.core.config import GenAiLogAnalysisServiceSettings
from app.core.dependencies import get_db_session
from app.main import create_app

MOCK_ANTHROPIC_PORT = 18701
MOCK_METRICS_PORT = 18702

_llm_mode = "success"  # "success" | "timeout" | "malformed" | "http_error"


def _build_mock_anthropic() -> FastAPI:
    mock = FastAPI()

    @mock.post("/v1/messages")
    async def messages(request: Request):
        import json as _json

        if _llm_mode == "timeout":
            await asyncio.sleep(30)  # will exceed the test's short LLM_TIMEOUT_SECONDS
        if _llm_mode == "http_error":
            return JSONResponse(status_code=500, content={"error": "internal"})
        if _llm_mode == "malformed":
            return {"content": [{"type": "text", "text": "not valid json{{{"}]}

        payload = {
            "root_cause_summary": "Database connection pool exhausted.",
            "human_explanation": "The service ran out of available database connections, causing new requests to fail.",
            "suggested_fix": "Increase the connection pool size or investigate long-running queries holding connections open.",
        }
        return {"content": [{"type": "text", "text": _json.dumps(payload)}]}

    return mock


def _build_mock_metrics() -> FastAPI:
    mock = FastAPI()

    @mock.get("/api/v1/metrics/query")
    async def query(
        service_id: str = Query(...), metric_name: str = Query(...), start: str = Query(...),
        end: str = Query(...), aggregation: str = Query(...), interval_seconds: int = Query(...),
    ):
        return {
            "service_id": service_id, "metric_name": metric_name, "aggregation": aggregation,
            "interval_seconds": interval_seconds,
            "points": [{"bucket_start": start, "value": 342.5}],
        }

    return mock


def _run_server(app: FastAPI, port: int):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            sync_httpx.post(f"http://127.0.0.1:{port}/v1/messages", json={}, timeout=0.3)
            break
        except Exception:
            try:
                sync_httpx.get(f"http://127.0.0.1:{port}/api/v1/metrics/query", params={"service_id": "x", "metric_name": "x", "start": "2024-01-01T00:00:00Z", "end": "2024-01-01T01:00:00Z", "aggregation": "avg", "interval_seconds": 60}, timeout=0.3)
                break
            except Exception:
                time.sleep(0.1)
    return server


@pytest.fixture(scope="session")
def mock_backends():
    anthropic_server = _run_server(_build_mock_anthropic(), MOCK_ANTHROPIC_PORT)
    metrics_server = _run_server(_build_mock_metrics(), MOCK_METRICS_PORT)
    yield {
        "anthropic_url": f"http://127.0.0.1:{MOCK_ANTHROPIC_PORT}",
        "metrics_url": f"http://127.0.0.1:{MOCK_METRICS_PORT}",
    }
    anthropic_server.should_exit = True
    metrics_server.should_exit = True


@pytest.fixture(autouse=True)
def reset_llm_mode():
    global _llm_mode
    _llm_mode = "success"
    yield
    _llm_mode = "success"


def set_llm_mode(mode: str):
    global _llm_mode
    _llm_mode = mode


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
    return GenAiLogAnalysisServiceSettings(
        DATABASE_URL="postgresql+asyncpg://platform:platform_local_dev_only@localhost:5432/genai_log_analysis_service_test",
        JWT_PUBLIC_KEY=public_key,
        REDIS_URL="redis://localhost:6379/3",
        LOG_STORE_MODE="memory",
        METRICS_SERVICE_URL=mock_backends["metrics_url"],
        ANTHROPIC_API_KEY="test-key",
        ANTHROPIC_API_URL=f"{mock_backends['anthropic_url']}/v1/messages",
        LLM_TIMEOUT_SECONDS=1.0,  # short, so the timeout test doesn't slow the suite
        ANALYSIS_CACHE_TTL_SECONDS=600,
        ENABLE_KAFKA_CONSUMER=False,
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
    import redis.asyncio as redis_lib

    from app.logstore.in_memory import InMemoryLogStore

    app = create_app()
    app.state.settings = settings
    app.state.http_client = httpx.AsyncClient()
    app.state.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    await app.state.redis.flushdb()
    app.state.log_store = InMemoryLogStore()

    async def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.http_client.aclose()
    await app.state.redis.aclose()
