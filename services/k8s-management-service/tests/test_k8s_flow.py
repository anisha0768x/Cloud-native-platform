from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions, subject="test-user"):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions, subject=subject)}"}


async def test_list_nodes_returns_demo_data(client, rsa_keypair):
    resp = await client.get("/api/v1/k8s/nodes", headers=auth_header(rsa_keypair, ["service:read"]))
    assert resp.status_code == 200
    nodes = resp.json()
    assert len(nodes) == 3
    assert all(n["status"] == "Ready" for n in nodes)


async def test_list_nodes_requires_permission(client, rsa_keypair):
    resp = await client.get("/api/v1/k8s/nodes")
    assert resp.status_code == 401


async def test_list_pods_reflects_deployment_replica_counts(client, rsa_keypair):
    resp = await client.get("/api/v1/k8s/pods", headers=auth_header(rsa_keypair, ["service:read"]))
    assert resp.status_code == 200
    pods = resp.json()
    checkout_pods = [p for p in pods if p["service_name"] == "checkout-api"]
    assert len(checkout_pods) == 3  # matches DemoClusterProvider's seeded replica count
    assert all(p["status"] == "Running" for p in checkout_pods)


async def test_list_pods_filters_by_namespace(client, rsa_keypair):
    resp = await client.get(
        "/api/v1/k8s/pods", params={"namespace": "monitoring"}, headers=auth_header(rsa_keypair, ["service:read"])
    )
    pods = resp.json()
    assert all(p["namespace"] == "monitoring" for p in pods)
    assert len(pods) == 1  # grafana, seeded with 1 replica


async def test_list_deployments(client, rsa_keypair):
    resp = await client.get("/api/v1/k8s/deployments", headers=auth_header(rsa_keypair, ["service:read"]))
    deployments = {d["name"]: d for d in resp.json()}
    assert deployments["checkout-api"]["desired_replicas"] == 3
    assert deployments["payments-api"]["desired_replicas"] == 2


async def test_scale_deployment_requires_permission(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/k8s/deployments/default/checkout-api/scale",
        json={"replicas": 5},
        headers=auth_header(rsa_keypair, ["service:read"]),  # wrong permission
    )
    assert resp.status_code == 403


async def test_scale_deployment_updates_replica_count(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/k8s/deployments/default/checkout-api/scale",
        json={"replicas": 5},
        headers=auth_header(rsa_keypair, ["scaling:trigger"]),
    )
    assert resp.status_code == 200
    assert resp.json()["desired_replicas"] == 5

    deployments_resp = await client.get(
        "/api/v1/k8s/deployments", headers=auth_header(rsa_keypair, ["service:read"])
    )
    deployments = {d["name"]: d for d in deployments_resp.json()}
    assert deployments["checkout-api"]["desired_replicas"] == 5

    pods_resp = await client.get("/api/v1/k8s/pods", headers=auth_header(rsa_keypair, ["service:read"]))
    checkout_pods = [p for p in pods_resp.json() if p["service_name"] == "checkout-api"]
    assert len(checkout_pods) == 5


async def test_scale_deployment_records_accurate_history(client, rsa_keypair):
    """The core correctness property: from_replicas must reflect the
    PRE-scale state, not get overwritten to equal to_replicas."""
    await client.post(
        "/api/v1/k8s/deployments/default/payments-api/scale",
        json={"replicas": 7},
        headers=auth_header(rsa_keypair, ["scaling:trigger"], subject="alice"),
    )

    resp = await client.get(
        "/api/v1/k8s/scaling-history",
        params={"deployment_name": "payments-api"},
        headers=auth_header(rsa_keypair, ["service:read"]),
    )
    history = resp.json()
    assert len(history) == 1
    entry = history[0]
    assert entry["from_replicas"] == 2  # payments-api's seeded starting replica count
    assert entry["to_replicas"] == 7
    assert entry["triggered_by"] == "alice"
    assert entry["trigger_source"] == "manual"


async def test_scale_nonexistent_deployment_returns_404(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/k8s/deployments/default/does-not-exist/scale",
        json={"replicas": 3},
        headers=auth_header(rsa_keypair, ["scaling:trigger"]),
    )
    assert resp.status_code == 404


async def test_scale_replicas_out_of_bounds_rejected(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/k8s/deployments/default/checkout-api/scale",
        json={"replicas": 500},  # exceeds the le=100 validation bound
        headers=auth_header(rsa_keypair, ["scaling:trigger"]),
    )
    assert resp.status_code == 422


async def test_snapshot_endpoint_returns_captured_data(client, rsa_keypair, db_session):
    """
    Triggers a snapshot directly via the service layer (bypassing the
    background worker, which is disabled in tests — see conftest) so the
    /snapshots query endpoint has something real to return.
    """
    from app.providers import build_cluster_provider
    from app.repositories.k8s_repository import K8sRepository
    from app.services.k8s_service import K8sService

    provider = build_cluster_provider("demo")
    service = K8sService(provider, K8sRepository(db_session))
    await service.capture_snapshot()

    now = datetime.now(timezone.utc)
    resp = await client.get(
        "/api/v1/k8s/snapshots",
        params={"start": (now - timedelta(minutes=5)).isoformat(), "end": (now + timedelta(minutes=5)).isoformat()},
        headers=auth_header(rsa_keypair, ["service:read"]),
    )
    assert resp.status_code == 200
    snapshots = resp.json()
    assert len(snapshots) == 1
    assert snapshots[0]["node_count"] == 3
    assert snapshots[0]["pod_count"] == 6  # 3 + 2 + 1 across seeded deployments
