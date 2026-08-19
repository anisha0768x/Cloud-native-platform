import pytest

from tests.conftest import get_received_slack, get_received_webhooks, make_token, set_webhook_failing

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions)}"}


async def test_send_requires_permission(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/notifications",
        json={"service_id": "checkout-api", "severity": "critical", "message": "down"},
        headers=auth_header(rsa_keypair, ["alert:read"]),
    )
    assert resp.status_code == 403


async def test_send_dispatches_to_all_three_real_channels(client, rsa_keypair, smtp_handler):
    resp = await client.post(
        "/api/v1/notifications",
        json={"service_id": "checkout-api", "severity": "critical", "message": "Service is down", "alert_id": "alert-123"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["delivery_attempts"]) == 3
    assert all(a["success"] for a in body["delivery_attempts"])
    channels = {a["channel"] for a in body["delivery_attempts"]}
    assert channels == {"webhook", "slack", "email"}

    # Real webhook payload actually received:
    webhooks = get_received_webhooks()
    assert len(webhooks) == 1
    assert webhooks[0]["service_id"] == "checkout-api"
    assert webhooks[0]["alert_id"] == "alert-123"

    # Real Slack-formatted payload actually received:
    slack_msgs = get_received_slack()
    assert len(slack_msgs) == 1
    assert "CRITICAL" in slack_msgs[0]["text"]
    assert "checkout-api" in slack_msgs[0]["text"]

    # Real email actually received by the local SMTP server:
    assert len(smtp_handler.received) == 1
    email = smtp_handler.received[0]
    assert email["mail_from"] == "alerts@platform.test"
    assert "oncall@platform.test" in email["rcpt_tos"]
    assert "Service is down" in email["content"]


async def test_partial_channel_failure_still_records_successes(client, rsa_keypair):
    set_webhook_failing(True)
    resp = await client.post(
        "/api/v1/notifications",
        json={"service_id": "payments-api", "severity": "warning", "message": "high latency"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )
    assert resp.status_code == 201  # NOT a failure overall
    body = resp.json()
    attempts_by_channel = {a["channel"]: a for a in body["delivery_attempts"]}
    assert attempts_by_channel["webhook"]["success"] is False
    assert attempts_by_channel["slack"]["success"] is True
    assert attempts_by_channel["email"]["success"] is True


async def test_notification_starts_pending(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/notifications",
        json={"service_id": "checkout-api", "severity": "info", "message": "deploy completed"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )
    assert resp.json()["status"] == "pending"
    assert resp.json()["acknowledged_at"] is None


async def test_acknowledge_updates_status(client, rsa_keypair):
    send_resp = await client.post(
        "/api/v1/notifications",
        json={"service_id": "checkout-api", "severity": "critical", "message": "down"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )
    notification_id = send_resp.json()["id"]

    ack_resp = await client.post(
        f"/api/v1/notifications/{notification_id}/acknowledge", headers=auth_header(rsa_keypair, ["alert:acknowledge"])
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "acknowledged"
    assert ack_resp.json()["acknowledged_at"] is not None


async def test_acknowledge_nonexistent_notification_returns_404(client, rsa_keypair):
    import uuid

    resp = await client.post(
        f"/api/v1/notifications/{uuid.uuid4()}/acknowledge", headers=auth_header(rsa_keypair, ["alert:acknowledge"])
    )
    assert resp.status_code == 404


async def test_history_filters_by_service_id(client, rsa_keypair):
    await client.post(
        "/api/v1/notifications",
        json={"service_id": "svc-a", "severity": "info", "message": "x"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )
    await client.post(
        "/api/v1/notifications",
        json={"service_id": "svc-b", "severity": "info", "message": "y"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )

    resp = await client.get(
        "/api/v1/notifications", params={"service_id": "svc-a"}, headers=auth_header(rsa_keypair, ["alert:read"])
    )
    results = resp.json()
    assert len(results) == 1
    assert results[0]["service_id"] == "svc-a"


async def test_history_filters_by_status(client, rsa_keypair):
    send_resp = await client.post(
        "/api/v1/notifications",
        json={"service_id": "svc-c", "severity": "critical", "message": "z"},
        headers=auth_header(rsa_keypair, ["notifications:send"]),
    )
    await client.post(
        f"/api/v1/notifications/{send_resp.json()['id']}/acknowledge", headers=auth_header(rsa_keypair, ["alert:acknowledge"])
    )

    pending = await client.get(
        "/api/v1/notifications", params={"status": "pending"}, headers=auth_header(rsa_keypair, ["alert:read"])
    )
    assert send_resp.json()["id"] not in [n["id"] for n in pending.json()]

    acknowledged = await client.get(
        "/api/v1/notifications", params={"status": "acknowledged"}, headers=auth_header(rsa_keypair, ["alert:read"])
    )
    assert send_resp.json()["id"] in [n["id"] for n in acknowledged.json()]
