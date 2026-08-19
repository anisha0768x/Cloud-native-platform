"""
Test fixtures.

WHY a REAL mock upstream (a tiny FastAPI app run by uvicorn on a real
port) instead of mocking httpx calls: the whole point of the gateway is
that it performs a real network hop to a real backend. Mocking that hop
away would leave the most important part of this module — proxying
headers/body/status correctly across an actual HTTP round-trip — entirely
untested.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Header, Request
from httpx import ASGITransport, AsyncClient

from platform_common.security import encode_token

from app.core.config import GatewaySettings
from app.main import create_app

MOCK_UPSTREAM_PORT = 18321


def _build_mock_upstream() -> FastAPI:
    """A minimal stand-in for a real backend service (Auth Service, etc.)."""
    mock = FastAPI()

    @mock.get("/api/v1/auth/me")
    async def me(authorization: str = Header(default="")):
        return {"authenticated": bool(authorization), "authorization_seen": authorization}

    @mock.post("/api/v1/auth/login")
    async def login():
        return {"access_token": "fake", "public_endpoint": True}

    @mock.get("/api/v1/auth/echo-headers")
    async def echo_headers(request: Request):
        return dict(request.headers)

    return mock


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


@pytest.fixture(scope="session")
def mock_upstream_server():
    """
    Runs the mock upstream in a background THREAD (its own event loop),
    not as an async pytest fixture — this avoids any dependency on which
    asyncio event loop a given test function happens to run under, since
    pytest-asyncio creates a fresh loop per test by default while this
    server needs to stay up for the whole session.
    """
    import threading
    import time

    import httpx as _httpx

    config = uvicorn.Config(_build_mock_upstream(), host="127.0.0.1", port=MOCK_UPSTREAM_PORT, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{MOCK_UPSTREAM_PORT}"
    for _ in range(50):
        try:
            resp = _httpx.get(f"{base_url}/api/v1/auth/me", timeout=0.2)
            if resp.status_code:
                break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("Mock upstream server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest_asyncio.fixture
async def gateway_client(mock_upstream_server, rsa_keypair):
    _, public_key = rsa_keypair
    settings = GatewaySettings(
        AUTH_SERVICE_URL=mock_upstream_server,
        JWT_PUBLIC_KEY=public_key,
        REDIS_URL="redis://localhost:6379/1",  # separate DB index from real usage
        RATE_LIMIT_REQUESTS=1000,  # generous default; specific tests override
    )

    app = create_app()

    async with app.router.lifespan_context(app):
        # Override with test-specific settings (mock upstream URL, test
        # keypair) AND rebuild the redis client/rate limiter to match —
        # otherwise the limiter would still point at the module-level
        # default settings' Redis DB, silently ignoring our test config.
        app.state.settings = settings
        await app.state.redis.aclose()

        import redis.asyncio as redis_lib

        from app.core.rate_limiter import RateLimiter

        app.state.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        app.state.rate_limiter = RateLimiter(
            app.state.redis, max_requests=settings.RATE_LIMIT_REQUESTS, window_seconds=60
        )
        await app.state.redis.flushdb()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway-test") as client:
            yield client


def make_token(rsa_keypair, *, expires_in=3600) -> str:
    private_key, _ = rsa_keypair
    return encode_token(
        private_key=private_key,
        subject=str(uuid.uuid4()),
        roles=["viewer"],
        permissions=["dashboard:read"],
        expires_in_seconds=expires_in,
    )
