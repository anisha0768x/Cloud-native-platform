import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions, **kwargs):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions, **kwargs)}"}


async def _register(client, rsa_keypair, name="checkout-api"):
    resp = await client.post(
        "/api/v1/services",
        json={"name": name, "type": "microservice", "namespace": "default"},
        headers=auth_header(rsa_keypair, ["service:create"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Registration & RBAC ---


async def test_register_service_requires_permission(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/services",
        json={"name": "x", "type": "microservice"},
        headers=auth_header(rsa_keypair, ["service:read"]),  # wrong permission
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_register_service_succeeds_with_correct_permission(client, rsa_keypair):
    service = await _register(client, rsa_keypair)
    assert service["name"] == "checkout-api"
    assert service["status"] == "unknown"


async def test_register_duplicate_name_rejected(client, rsa_keypair):
    await _register(client, rsa_keypair, name="dup-service")
    resp = await client.post(
        "/api/v1/services",
        json={"name": "dup-service", "type": "microservice"},
        headers=auth_header(rsa_keypair, ["service:create"]),
    )
    assert resp.status_code == 409


async def test_list_services_requires_read_permission(client, rsa_keypair):
    await _register(client, rsa_keypair, name="listed-service")
    resp = await client.get("/api/v1/services", headers=auth_header(rsa_keypair, ["service:read"]))
    assert resp.status_code == 200
    assert any(s["name"] == "listed-service" for s in resp.json())


async def test_unauthenticated_request_rejected(client):
    resp = await client.get("/api/v1/services")
    assert resp.status_code == 401


# --- Heartbeat state machine (the core business logic) ---


async def test_healthy_heartbeat_sets_status_healthy(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-healthy")
    resp = await client.post(
        f"/api/v1/services/{service['id']}/heartbeat",
        json={"healthy": True, "latency_ms": 42},
        headers=auth_header(rsa_keypair, ["service:update"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["service_status"] == "healthy"
    assert body["consecutive_failed_heartbeats"] == 0


async def test_single_failed_heartbeat_sets_degraded_not_down(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-degraded")
    resp = await client.post(
        f"/api/v1/services/{service['id']}/heartbeat",
        json={"healthy": False, "detail": "connection timeout"},
        headers=auth_header(rsa_keypair, ["service:update"]),
    )
    body = resp.json()
    assert body["service_status"] == "degraded"
    assert body["alert_created"] is False


async def test_threshold_consecutive_failures_marks_down_and_creates_alert(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-down")
    headers = auth_header(rsa_keypair, ["service:update"])

    for _ in range(2):
        resp = await client.post(
            f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": False}, headers=headers
        )
        assert resp.json()["alert_created"] is False

    # 3rd consecutive failure crosses the threshold (default 3).
    resp = await client.post(
        f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": False}, headers=headers
    )
    body = resp.json()
    assert body["service_status"] == "down"
    assert body["alert_created"] is True


async def test_down_alert_not_duplicated_on_further_failures(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-flapping")
    headers = auth_header(rsa_keypair, ["service:update"])

    for _ in range(5):  # well past the threshold of 3
        resp = await client.post(
            f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": False}, headers=headers
        )

    alerts_resp = await client.get(
        "/api/v1/alerts",
        params={"service_id": service["id"], "type": "service_down"},
        headers=auth_header(rsa_keypair, ["alert:read"]),
    )
    open_alerts = [a for a in alerts_resp.json() if a["type"] == "service_down"]
    assert len(open_alerts) == 1  # not 5


async def test_recovery_after_down_resets_to_healthy(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-recovers")
    headers = auth_header(rsa_keypair, ["service:update"])

    for _ in range(3):
        await client.post(f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": False}, headers=headers)

    resp = await client.post(
        f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": True}, headers=headers
    )
    body = resp.json()
    assert body["service_status"] == "healthy"
    assert body["consecutive_failed_heartbeats"] == 0


async def test_health_summary_computes_uptime_percentage(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-summary")
    headers = auth_header(rsa_keypair, ["service:update"])

    # 3 healthy, 1 failed => 75% uptime over the considered window
    for healthy in [True, True, True, False]:
        await client.post(f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": healthy}, headers=headers)

    resp = await client.get(
        f"/api/v1/services/{service['id']}/health-summary",
        headers=auth_header(rsa_keypair, ["service:read"]),
    )
    body = resp.json()
    assert body["uptime_percentage"] == 75.0
    assert body["checks_considered"] == 4


# --- Alerts lifecycle ---


async def test_acknowledge_alert(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-ack")
    headers = auth_header(rsa_keypair, ["service:update"])
    for _ in range(3):
        await client.post(f"/api/v1/services/{service['id']}/heartbeat", json={"healthy": False}, headers=headers)

    alerts = (
        await client.get(
            "/api/v1/alerts",
            params={"service_id": service["id"]},
            headers=auth_header(rsa_keypair, ["alert:read"]),
        )
    ).json()
    alert_id = alerts[0]["id"]

    resp = await client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        headers=auth_header(rsa_keypair, ["alert:acknowledge"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_by"] == "test-user"


async def test_delete_service_requires_permission_and_cascades(client, rsa_keypair):
    service = await _register(client, rsa_keypair, name="svc-delete-me")

    denied = await client.delete(
        f"/api/v1/services/{service['id']}", headers=auth_header(rsa_keypair, ["service:read"])
    )
    assert denied.status_code == 403

    resp = await client.delete(
        f"/api/v1/services/{service['id']}", headers=auth_header(rsa_keypair, ["service:delete"])
    )
    assert resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/services/{service['id']}", headers=auth_header(rsa_keypair, ["service:read"])
    )
    assert get_resp.status_code == 404
