import asyncio

import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


async def test_public_path_proxied_without_token(gateway_client):
    resp = await gateway_client.post("/api/v1/auth/login", json={})
    assert resp.status_code == 200
    assert resp.json()["public_endpoint"] is True


async def test_protected_path_rejected_without_token(gateway_client):
    resp = await gateway_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_protected_path_rejected_with_malformed_header(gateway_client):
    resp = await gateway_client.get("/api/v1/auth/me", headers={"Authorization": "NotBearer xyz"})
    assert resp.status_code == 401


async def test_protected_path_rejected_with_invalid_token(gateway_client):
    resp = await gateway_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


async def test_protected_path_accepted_and_proxied_with_valid_token(gateway_client, rsa_keypair):
    token = make_token(rsa_keypair)
    resp = await gateway_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    # The ORIGINAL bearer token must reach the backend unmodified — the
    # backend independently re-verifies it (defense in depth), so the
    # gateway must not strip or rewrite the Authorization header.
    assert body["authorization_seen"] == f"Bearer {token}"


async def test_expired_token_rejected(gateway_client, rsa_keypair):
    token = make_token(rsa_keypair, expires_in=-10)
    resp = await gateway_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_unknown_route_returns_404(gateway_client, rsa_keypair):
    token = make_token(rsa_keypair)
    resp = await gateway_client.get("/api/v1/nonexistent-service/ping", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_trace_id_is_generated_and_propagated_to_upstream(gateway_client, rsa_keypair):
    token = make_token(rsa_keypair)
    resp = await gateway_client.get(
        "/api/v1/auth/echo-headers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    # Gateway's own response header:
    assert "x-trace-id" in resp.headers
    # And the upstream (mock) actually received it as a forwarded header:
    upstream_headers = {k.lower(): v for k, v in resp.json().items()}
    assert upstream_headers.get("x-trace-id") == resp.headers["x-trace-id"]
    assert upstream_headers.get("x-forwarded-by") == "api-gateway"


async def test_caller_supplied_trace_id_is_preserved(gateway_client, rsa_keypair):
    token = make_token(rsa_keypair)
    resp = await gateway_client.get(
        "/api/v1/auth/echo-headers",
        headers={"Authorization": f"Bearer {token}", "X-Trace-Id": "caller-supplied-id-123"},
    )
    assert resp.headers["x-trace-id"] == "caller-supplied-id-123"


async def test_rate_limit_blocks_after_threshold(mock_upstream_server, rsa_keypair):
    """
    Uses its own tightly-limited gateway instance (rather than the shared
    `gateway_client` fixture's generous default) so this test doesn't
    interfere with the others sharing the same Redis DB.
    """
    from httpx import ASGITransport, AsyncClient

    from app.core.config import GatewaySettings
    from app.core.rate_limiter import RateLimiter
    from app.main import create_app

    _, public_key = rsa_keypair
    settings = GatewaySettings(
        AUTH_SERVICE_URL=mock_upstream_server,
        JWT_PUBLIC_KEY=public_key,
        REDIS_URL="redis://localhost:6379/1",
        RATE_LIMIT_REQUESTS=3,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.settings = settings
        await app.state.redis.aclose()
        import redis.asyncio as redis_lib

        app.state.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        app.state.rate_limiter = RateLimiter(app.state.redis, max_requests=3, window_seconds=60)
        await app.state.redis.flushdb()

        token = make_token(rsa_keypair)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway-test") as client:
            headers = {"Authorization": f"Bearer {token}"}
            statuses = [
                (await client.get("/api/v1/auth/me", headers=headers)).status_code for _ in range(4)
            ]
            assert statuses == [200, 200, 200, 429]


async def test_upstream_unreachable_returns_503(rsa_keypair):
    """Points the gateway at a port nothing is listening on."""
    from httpx import ASGITransport, AsyncClient

    from app.core.config import GatewaySettings
    from app.core.rate_limiter import RateLimiter
    from app.main import create_app

    _, public_key = rsa_keypair
    settings = GatewaySettings(
        AUTH_SERVICE_URL="http://127.0.0.1:1",  # nothing listens here
        JWT_PUBLIC_KEY=public_key,
        REDIS_URL="redis://localhost:6379/1",
        UPSTREAM_TIMEOUT_SECONDS=2.0,
    )
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.settings = settings
        await app.state.redis.aclose()
        import redis.asyncio as redis_lib

        app.state.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        app.state.rate_limiter = RateLimiter(app.state.redis, max_requests=1000, window_seconds=60)
        await app.state.redis.flushdb()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://gateway-test") as client:
            resp = await client.post("/api/v1/auth/login", json={})
            assert resp.status_code == 503
            assert resp.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
