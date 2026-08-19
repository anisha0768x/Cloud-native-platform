"""
WHY real threaded mock backend servers (not mocked httpx calls): the
entire point of this service is orchestrating real HTTP calls across
services and degrading gracefully when one fails — mocking away the HTTP
layer would leave exactly the part worth testing untested. Same pattern
used for the API Gateway's tests (see services/api-gateway/tests/conftest.py).
"""

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
from fastapi import FastAPI, Header, Query
from httpx import ASGITransport, AsyncClient

from platform_common.security import encode_token

from app.core.config import DashboardServiceSettings
from app.main import create_app

MONITORING_PORT = 18401
K8S_PORT = 18402

# --- Mock backend state, mutated per-test via module-level flags ---
_monitoring_should_fail = False


def _build_mock_monitoring() -> FastAPI:
    mock = FastAPI()

    @mock.get("/api/v1/services")
    async def services(authorization: str = Header(default="")):
        if _monitoring_should_fail:
            raise sync_httpx.ConnectError("simulated monitoring outage")
        return [
            {"name": "checkout-api", "status": "healthy", "namespace": "default"},
            {"name": "payments-api", "status": "degraded", "namespace": "default"},
            {"name": "grafana", "status": "healthy", "namespace": "monitoring"},
        ]

    @mock.get("/api/v1/alerts")
    async def alerts(status: str | None = Query(default=None)):
        if _monitoring_should_fail:
            raise sync_httpx.ConnectError("simulated monitoring outage")
        return [{"severity": "critical", "status": "open"}, {"severity": "warning", "status": "open"}]

    return mock


def _build_mock_k8s() -> FastAPI:
    mock = FastAPI()

    @mock.get("/api/v1/k8s/nodes")
    async def nodes():
        return [{"name": "node-1", "status": "Ready"}, {"name": "node-2", "status": "Ready"}]

    @mock.get("/api/v1/k8s/pods")
    async def pods():
        return [{"name": f"pod-{i}", "status": "Running"} for i in range(5)]

    @mock.get("/api/v1/k8s/deployments")
    async def deployments():
        return [{"name": "checkout-api", "desired_replicas": 3}]

    @mock.get("/api/v1/k8s/scaling-history")
    async def scaling_history():
        return [{"deployment_name": "checkout-api", "from_replicas": 2, "to_replicas": 3}]

    @mock.get("/api/v1/k8s/snapshots")
    async def snapshots():
        return [{"node_count": 2, "pod_count": 5}]

    return mock


def _run_server_in_thread(app: FastAPI, port: int):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            sync_httpx.get(f"http://127.0.0.1:{port}/api/v1/k8s/nodes", timeout=0.2)
            break
        except Exception:
            try:
                sync_httpx.get(f"http://127.0.0.1:{port}/api/v1/services", timeout=0.2)
                break
            except Exception:
                time.sleep(0.1)
    return server, thread


@pytest.fixture(scope="session")
def mock_backends():
    monitoring_server, _ = _run_server_in_thread(_build_mock_monitoring(), MONITORING_PORT)
    k8s_server, _ = _run_server_in_thread(_build_mock_k8s(), K8S_PORT)
    yield {
        "monitoring_url": f"http://127.0.0.1:{MONITORING_PORT}",
        "k8s_url": f"http://127.0.0.1:{K8S_PORT}",
    }
    monitoring_server.should_exit = True
    k8s_server.should_exit = True


@pytest.fixture(autouse=True)
def reset_monitoring_failure_flag():
    global _monitoring_should_fail
    _monitoring_should_fail = False
    yield
    _monitoring_should_fail = False


def set_monitoring_failing(value: bool):
    global _monitoring_should_fail
    _monitoring_should_fail = value


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
        roles=["viewer"],
        permissions=permissions,
        expires_in_seconds=3600,
    )


@pytest_asyncio.fixture
async def client(mock_backends, rsa_keypair):
    _, public_key = rsa_keypair
    settings = DashboardServiceSettings(
        MONITORING_SERVICE_URL=mock_backends["monitoring_url"],
        K8S_MANAGEMENT_SERVICE_URL=mock_backends["k8s_url"],
        JWT_PUBLIC_KEY=public_key,
        REDIS_URL="redis://localhost:6379/2",  # isolated DB index for this service's tests
        CACHE_TTL_SECONDS=15,
    )

    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.settings = settings
        # Rebuild the redis client to match THIS test's settings (isolated
        # DB index) — the one built during lifespan_context used the
        # module-level settings' REDIS_URL, not this fixture's override.
        await app.state.redis.aclose()
        import redis.asyncio as redis_lib

        app.state.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        await app.state.redis.flushdb()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
