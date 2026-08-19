"""
End-to-end tests against the real HTTP layer (via httpx ASGITransport) and
a real Postgres transaction. This is deliberately the heaviest-weight test
file — it's the one that proves the whole vertical slice (router ->
service -> repository -> DB -> JWT) actually works together, not just each
layer in isolation.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def _register_and_login(client, email="alice@example.com", password="Sup3rSecret"):
    reg = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Alice Example"}
    )
    assert reg.status_code == 201, reg.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()


async def test_register_creates_user_with_default_viewer_role(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "Str0ngPass", "full_name": "Bob"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "bob@example.com"
    assert "viewer" in body["roles"]
    assert "password" not in body and "password_hash" not in body


async def test_register_rejects_duplicate_email(client):
    await client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "Str0ngPass"})
    resp = await client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "Str0ngPass"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_register_rejects_weak_password(client):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "weak@example.com", "password": "alllowercase"}
    )
    assert resp.status_code == 422


async def test_login_success_returns_valid_token_pair(client):
    tokens = await _register_and_login(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] == 900


async def test_login_wrong_password_rejected(client):
    await client.post("/api/v1/auth/register", json={"email": "carol@example.com", "password": "Str0ngPass"})
    resp = await client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "WrongPass1"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_login_nonexistent_user_and_wrong_password_give_identical_error(client):
    """Prevents user enumeration via distinguishable error messages."""
    await client.post("/api/v1/auth/register", json={"email": "dave@example.com", "password": "Str0ngPass"})
    resp_wrong_pw = await client.post("/api/v1/auth/login", json={"email": "dave@example.com", "password": "Nope12345"})
    resp_no_user = await client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "Nope12345"})
    assert resp_wrong_pw.json()["error"]["message"] == resp_no_user.json()["error"]["message"]


async def test_account_locks_after_max_failed_attempts(client):
    await client.post("/api/v1/auth/register", json={"email": "erin@example.com", "password": "Str0ngPass"})
    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"email": "erin@example.com", "password": "WrongOne1"})
    # 6th attempt, even with the CORRECT password, must be rejected due to lockout.
    resp = await client.post("/api/v1/auth/login", json={"email": "erin@example.com", "password": "Str0ngPass"})
    assert resp.status_code == 401
    assert "locked" in resp.json()["error"]["message"].lower()


async def test_me_endpoint_returns_authenticated_user(client):
    tokens = await _register_and_login(client, email="frank@example.com")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "frank@example.com"


async def test_me_endpoint_rejects_missing_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_refresh_issues_new_working_token_and_rotates_old_one(client):
    tokens = await _register_and_login(client, email="grace@example.com")

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["access_token"] != tokens["access_token"]

    # Old refresh token must now be dead (rotation).
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401

    # New access token must actually work.
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
    assert me.status_code == 200


async def test_logout_revokes_refresh_token(client):
    tokens = await _register_and_login(client, email="heidi@example.com")
    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 204

    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401
