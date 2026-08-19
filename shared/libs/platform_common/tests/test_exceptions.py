"""
Verifies the standard error envelope every service returns.
Run with: pytest (from shared/libs/platform_common)
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_common.exceptions import NotFoundError, register_exception_handlers


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise NotFoundError("Service 'checkout-api' not found", details={"service_id": "abc123"})

    @app.get("/unexpected")
    async def unexpected():
        raise ValueError("something truly unplanned")

    return app


def test_platform_error_returns_standard_envelope():
    client = TestClient(_build_test_app())
    resp = client.get("/boom")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert body["error"]["message"] == "Service 'checkout-api' not found"
    assert body["error"]["details"] == {"service_id": "abc123"}


def test_unhandled_exception_does_not_leak_internals():
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/unexpected")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "something truly unplanned" not in body["error"]["message"]
