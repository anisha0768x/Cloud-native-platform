"""
Regression test for the require_permission bug found while building
Monitoring Service (Module 4): the original implementation relied on
FastAPI's bare `Depends()` shortcut to source a TokenPayload, which
doesn't work — FastAPI has no way to construct a TokenPayload from request
data. This test exercises the FULL path (real HTTP request -> dependency
resolution -> permission check) so a similar regression can't ship again
unnoticed.
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from platform_common.exceptions import register_exception_handlers
from platform_common.security import encode_token, require_permission


def _build_test_app(public_key: str) -> FastAPI:
    app = FastAPI()
    app.state.settings = type("S", (), {"JWT_PUBLIC_KEY": public_key})()
    register_exception_handlers(app)

    @app.get("/protected", dependencies=[Depends(require_permission("service:create"))])
    async def protected():
        return {"ok": True}

    return app


def _keypair():
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


def test_require_permission_allows_matching_permission():
    private_key, public_key = _keypair()
    client = TestClient(_build_test_app(public_key))
    token = encode_token(
        private_key=private_key,
        subject="user-1",
        roles=["operator"],
        permissions=["service:create"],
        expires_in_seconds=3600,
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_require_permission_rejects_missing_permission():
    private_key, public_key = _keypair()
    client = TestClient(_build_test_app(public_key))
    token = encode_token(
        private_key=private_key,
        subject="user-1",
        roles=["viewer"],
        permissions=["service:read"],  # lacks service:create
        expires_in_seconds=3600,
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_require_permission_admin_wildcard_bypasses_check():
    private_key, public_key = _keypair()
    client = TestClient(_build_test_app(public_key))
    token = encode_token(
        private_key=private_key,
        subject="admin-1",
        roles=["admin"],
        permissions=["admin:*"],
        expires_in_seconds=3600,
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_require_permission_rejects_missing_token():
    _, public_key = _keypair()
    client = TestClient(_build_test_app(public_key))
    resp = client.get("/protected")
    assert resp.status_code == 401
