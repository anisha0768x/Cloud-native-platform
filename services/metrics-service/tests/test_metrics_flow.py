import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions)}"}


async def test_ingest_requires_permission(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/metrics/ingest",
        json={"service_id": str(uuid.uuid4()), "metric_name": "cpu_usage", "value": 42.0},
        headers=auth_header(rsa_keypair, ["metrics:read"]),  # wrong permission
    )
    assert resp.status_code == 403


async def test_ingest_accepts_valid_metric(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/metrics/ingest",
        json={"service_id": str(uuid.uuid4()), "metric_name": "cpu_usage", "value": 55.5},
        headers=auth_header(rsa_keypair, ["metrics:write"]),
    )
    assert resp.status_code == 201
    assert resp.json()["accepted"] is True


async def test_ingest_defaults_timestamp_to_now(client, rsa_keypair):
    before = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/v1/metrics/ingest",
        json={"service_id": str(uuid.uuid4()), "metric_name": "latency_ms", "value": 12.0},
        headers=auth_header(rsa_keypair, ["metrics:write"]),
    )
    after = datetime.now(timezone.utc)
    recorded_time = datetime.fromisoformat(resp.json()["time"])
    assert before <= recorded_time <= after + timedelta(seconds=1)


async def test_latest_returns_most_recent_point(client, rsa_keypair):
    service_id = str(uuid.uuid4())
    headers = auth_header(rsa_keypair, ["metrics:write"])

    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    new_time = datetime.now(timezone.utc).isoformat()

    await client.post(
        "/api/v1/metrics/ingest",
        json={"service_id": service_id, "metric_name": "cpu_usage", "value": 10.0, "timestamp": old_time},
        headers=headers,
    )
    await client.post(
        "/api/v1/metrics/ingest",
        json={"service_id": service_id, "metric_name": "cpu_usage", "value": 99.0, "timestamp": new_time},
        headers=headers,
    )

    resp = await client.get(
        "/api/v1/metrics/latest",
        params={"service_id": service_id, "metric_name": "cpu_usage"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == 99.0


async def test_latest_returns_404_when_no_data(client, rsa_keypair):
    resp = await client.get(
        "/api/v1/metrics/latest",
        params={"service_id": str(uuid.uuid4()), "metric_name": "nonexistent"},
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    assert resp.status_code == 404


async def test_query_aggregation_avg_is_mathematically_correct(client, rsa_keypair):
    """
    The whole point of this service is correct aggregation — this test
    verifies actual arithmetic, not just a 200 status code. Values
    10, 20, 30 in the SAME bucket must average to exactly 20.
    """
    service_id = str(uuid.uuid4())
    headers = auth_header(rsa_keypair, ["metrics:write"])
    base_time = datetime.now(timezone.utc).replace(microsecond=0)

    for i, value in enumerate([10.0, 20.0, 30.0]):
        ts = (base_time + timedelta(seconds=i)).isoformat()
        await client.post(
            "/api/v1/metrics/ingest",
            json={"service_id": service_id, "metric_name": "memory_pct", "value": value, "timestamp": ts},
            headers=headers,
        )

    resp = await client.get(
        "/api/v1/metrics/query",
        params={
            "service_id": service_id,
            "metric_name": "memory_pct",
            "start": base_time.isoformat(),
            "end": (base_time + timedelta(minutes=1)).isoformat(),
            "aggregation": "avg",
            "interval_seconds": 60,  # all 3 points fall in one 60s bucket
        },
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["value"] == 20.0


async def test_query_buckets_split_correctly_across_intervals(client, rsa_keypair):
    """Two points 120 seconds apart with a 60s interval must land in DIFFERENT buckets."""
    service_id = str(uuid.uuid4())
    headers = auth_header(rsa_keypair, ["metrics:write"])
    base_time = datetime.now(timezone.utc).replace(microsecond=0)

    await client.post(
        "/api/v1/metrics/ingest",
        json={
            "service_id": service_id,
            "metric_name": "request_count",
            "value": 5.0,
            "timestamp": base_time.isoformat(),
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/metrics/ingest",
        json={
            "service_id": service_id,
            "metric_name": "request_count",
            "value": 7.0,
            "timestamp": (base_time + timedelta(seconds=120)).isoformat(),
        },
        headers=headers,
    )

    resp = await client.get(
        "/api/v1/metrics/query",
        params={
            "service_id": service_id,
            "metric_name": "request_count",
            "start": base_time.isoformat(),
            "end": (base_time + timedelta(minutes=5)).isoformat(),
            "aggregation": "sum",
            "interval_seconds": 60,
        },
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    points = resp.json()["points"]
    assert len(points) == 2
    assert {p["value"] for p in points} == {5.0, 7.0}


async def test_query_rejects_end_before_start(client, rsa_keypair):
    now = datetime.now(timezone.utc)
    resp = await client.get(
        "/api/v1/metrics/query",
        params={
            "service_id": str(uuid.uuid4()),
            "metric_name": "cpu_usage",
            "start": now.isoformat(),
            "end": (now - timedelta(hours=1)).isoformat(),
        },
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_query_rejects_excessive_range(client, rsa_keypair):
    now = datetime.now(timezone.utc)
    resp = await client.get(
        "/api/v1/metrics/query",
        params={
            "service_id": str(uuid.uuid4()),
            "metric_name": "cpu_usage",
            "start": (now - timedelta(days=200)).isoformat(),
            "end": now.isoformat(),
        },
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    assert resp.status_code == 422


async def test_p95_aggregation(client, rsa_keypair):
    service_id = str(uuid.uuid4())
    headers = auth_header(rsa_keypair, ["metrics:write"])
    base_time = datetime.now(timezone.utc).replace(microsecond=0)

    # 100 evenly spread values 1..100 => p95 should be close to 95-96
    for i in range(1, 101):
        ts = (base_time + timedelta(milliseconds=i)).isoformat()
        await client.post(
            "/api/v1/metrics/ingest",
            json={"service_id": service_id, "metric_name": "latency_ms", "value": float(i), "timestamp": ts},
            headers=headers,
        )

    resp = await client.get(
        "/api/v1/metrics/query",
        params={
            "service_id": service_id,
            "metric_name": "latency_ms",
            "start": base_time.isoformat(),
            "end": (base_time + timedelta(minutes=1)).isoformat(),
            "aggregation": "p95",
            "interval_seconds": 60,
        },
        headers=auth_header(rsa_keypair, ["metrics:read"]),
    )
    p95_value = resp.json()["points"][0]["value"]
    assert 94.0 <= p95_value <= 96.0
