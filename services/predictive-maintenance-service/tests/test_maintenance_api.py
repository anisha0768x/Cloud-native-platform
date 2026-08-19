import uuid

import pytest

from tests.conftest import make_token, set_cpu_level

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions)}"}


async def test_predict_requires_permission(client, rsa_keypair):
    resp = await client.get(
        f"/api/v1/predictions/maintenance/{uuid.uuid4()}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["service:read"]),
    )
    assert resp.status_code == 403


async def test_predict_returns_valid_response_with_live_data(client, rsa_keypair):
    service_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/predictions/maintenance/{service_id}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["failure_probability"] <= 1.0
    assert body["root_cause"]
    assert body["recommendation"]
    # restart_count should reflect the SUM of checkout-api's 2 pods (2+1=3),
    # not other-service's 9 — proves the service_name filter works correctly.
    assert body["feature_snapshot"]["restart_count"] == 3


async def test_predict_uses_real_metrics_data_points(client, rsa_keypair):
    service_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/predictions/maintenance/{service_id}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    body = resp.json()
    assert body["feature_snapshot"]["cpu_data_points"] == 6  # mock returns 6 hourly points


async def test_high_cpu_scenario_predicts_higher_risk_than_low_cpu(client, rsa_keypair):
    """
    End-to-end proof that the whole pipeline (live data fetch -> feature
    engineering -> trained model) responds correctly to a real change in
    upstream data, not just to hand-crafted FeatureVectors in unit tests.
    """
    set_cpu_level("low")
    low_resp = await client.get(
        f"/api/v1/predictions/maintenance/{uuid.uuid4()}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )

    set_cpu_level("high")
    high_resp = await client.get(
        f"/api/v1/predictions/maintenance/{uuid.uuid4()}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )

    assert high_resp.json()["failure_probability"] > low_resp.json()["failure_probability"]


async def test_prediction_persisted_and_appears_in_history(client, rsa_keypair):
    service_id = uuid.uuid4()
    predict_resp = await client.get(
        f"/api/v1/predictions/maintenance/{service_id}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    history_resp = await client.get(
        f"/api/v1/predictions/maintenance/{service_id}/history", headers=auth_header(rsa_keypair, ["metrics:read"])
    )
    history = history_resp.json()
    assert len(history) == 1
    assert history[0]["failure_probability"] == predict_resp.json()["failure_probability"]


async def test_history_isolated_per_service(client, rsa_keypair):
    service_a = uuid.uuid4()
    service_b = uuid.uuid4()
    await client.get(
        f"/api/v1/predictions/maintenance/{service_a}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    await client.get(
        f"/api/v1/predictions/maintenance/{service_b}",
        params={"service_name": "checkout-api"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    history_a = (
        await client.get(
            f"/api/v1/predictions/maintenance/{service_a}/history", headers=auth_header(rsa_keypair, ["metrics:read"])
        )
    ).json()
    assert len(history_a) == 1
    assert history_a[0]["service_id"] == str(service_a)
