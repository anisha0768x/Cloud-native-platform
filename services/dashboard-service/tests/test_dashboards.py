import pytest

from tests.conftest import make_token, set_monitoring_failing

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions)}"}


async def test_executive_dashboard_requires_permission(client, rsa_keypair):
    resp = await client.get("/api/v1/dashboards/executive", headers=auth_header(rsa_keypair, ["service:read"]))
    assert resp.status_code == 403


async def test_executive_dashboard_aggregates_correctly(client, rsa_keypair):
    resp = await client.get("/api/v1/dashboards/executive", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    assert resp.status_code == 200
    body = resp.json()

    # 3 services total (from mock monitoring), 2 healthy, 1 degraded => 2/3 = 66.67%
    assert body["total_services"] == 3
    assert body["services_by_status"] == {"healthy": 2, "degraded": 1}
    assert body["overall_health_percentage"] == 66.67

    # 2 open alerts: 1 critical, 1 warning
    assert body["open_alerts_by_severity"] == {"critical": 1, "warning": 1}

    # From mock k8s: 2 nodes, 1 deployment, 5 pods
    assert body["cluster_node_count"] == 2
    assert body["cluster_deployment_count"] == 1
    assert body["cluster_pod_count"] == 5
    assert body["partial_errors"] == []


async def test_executive_dashboard_degrades_gracefully_on_backend_failure(client, rsa_keypair):
    set_monitoring_failing(True)
    resp = await client.get("/api/v1/dashboards/executive", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    assert resp.status_code == 200  # NOT a 500 — this is the whole point of graceful degradation
    body = resp.json()

    # Monitoring's data is missing/defaulted...
    assert body["total_services"] == 0
    assert "monitoring:services" in body["partial_errors"]
    assert "monitoring:alerts" in body["partial_errors"]

    # ...but K8s data, which didn't fail, still came through correctly.
    assert body["cluster_node_count"] == 2
    assert "k8s:nodes" not in body["partial_errors"]


async def test_executive_dashboard_is_cached(client, rsa_keypair):
    """
    Second call within the TTL window must return the SAME cached
    response even if the backend's data would have changed — proves the
    cache is actually being hit, not just present but bypassed.
    """
    first = await client.get("/api/v1/dashboards/executive", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    assert first.json()["total_services"] == 3

    set_monitoring_failing(True)  # would change the result if the cache weren't hit
    second = await client.get("/api/v1/dashboards/executive", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    assert second.json()["total_services"] == 3  # still the cached value, not degraded
    assert second.json() == first.json()


async def test_infrastructure_dashboard(client, rsa_keypair):
    resp = await client.get("/api/v1/dashboards/infrastructure", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 2
    assert len(body["services_health"]) == 3
    assert body["services_health"][0]["name"] == "checkout-api"
    assert len(body["cluster_snapshot_trend"]) == 1


async def test_kubernetes_dashboard(client, rsa_keypair):
    resp = await client.get("/api/v1/dashboards/kubernetes", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["pods"]) == 5
    assert len(body["deployments"]) == 1
    assert len(body["recent_scaling_history"]) == 1


async def test_dashboards_use_independent_cache_keys(client, rsa_keypair):
    """Fetching one dashboard must not populate another's cache slot."""
    await client.get("/api/v1/dashboards/kubernetes", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    set_monitoring_failing(True)
    exec_resp = await client.get("/api/v1/dashboards/executive", headers=auth_header(rsa_keypair, ["dashboard:read"]))
    # Executive dashboard was NOT cached by the kubernetes-dashboard call,
    # so it still reflects the (now-failing) monitoring backend.
    assert "monitoring:services" in exec_resp.json()["partial_errors"]
