import uuid

import pytest

from tests.conftest import make_token, set_llm_mode

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions)}"}


async def _ingest_error_log(client, rsa_keypair, service_id, message="Connection to database timed out"):
    resp = await client.post(
        "/api/v1/logs/ingest",
        json={"service_id": str(service_id), "level": "ERROR", "message": message},
        headers=auth_header(rsa_keypair, ["logs:write"]),
    )
    assert resp.status_code == 201, resp.text


# --- Log ingestion / search ---


async def test_log_ingest_requires_permission(client, rsa_keypair):
    resp = await client.post(
        "/api/v1/logs/ingest",
        json={"service_id": str(uuid.uuid4()), "level": "ERROR", "message": "x"},
        headers=auth_header(rsa_keypair, ["logs:read"]),
    )
    assert resp.status_code == 403


async def test_log_search_finds_ingested_entry(client, rsa_keypair):
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id, message="disk full on /var/log")

    resp = await client.get(
        "/api/v1/logs/search", params={"service_id": str(service_id)}, headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert "disk full" in results[0]["message"]


# --- GenAI analysis: LLM success path ---


async def test_analyze_requires_permission(client, rsa_keypair):
    resp = await client.get(
        f"/api/v1/genai/analyze/{uuid.uuid4()}", headers=auth_header(rsa_keypair, ["service:read"])
    )
    assert resp.status_code == 403


async def test_analyze_uses_llm_when_available(client, rsa_keypair):
    set_llm_mode("success")
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id)

    resp = await client.get(
        f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "llm"
    assert "connection pool" in body["root_cause_summary"].lower()
    assert body["logs_analyzed"] == 1
    assert body["cached"] is False


async def test_analyze_with_no_logs_still_succeeds(client, rsa_keypair):
    resp = await client.get(
        f"/api/v1/genai/analyze/{uuid.uuid4()}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200  # never a blank/error panel, even with zero data


# --- GenAI analysis: fallback paths (the most important correctness property) ---


async def test_analyze_falls_back_on_llm_timeout(client, rsa_keypair):
    set_llm_mode("timeout")
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id)

    resp = await client.get(
        f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200  # NOT a 500 — graceful degradation
    body = resp.json()
    assert body["source"] == "fallback"
    assert "1 error log" in body["root_cause_summary"]


async def test_analyze_falls_back_on_malformed_llm_response(client, rsa_keypair):
    set_llm_mode("malformed")
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id)

    resp = await client.get(
        f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "fallback"


async def test_analyze_falls_back_on_llm_http_error(client, rsa_keypair):
    set_llm_mode("http_error")
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id)

    resp = await client.get(
        f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "fallback"


async def test_analyze_falls_back_when_no_api_key_configured(client, rsa_keypair, settings):
    """The AnthropicClient itself refuses to call out with no key — same fallback path."""
    settings.ANTHROPIC_API_KEY = None
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id)

    resp = await client.get(
        f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "fallback"


async def test_fallback_with_zero_errors_reports_no_incident(client, rsa_keypair):
    set_llm_mode("timeout")
    resp = await client.get(
        f"/api/v1/genai/analyze/{uuid.uuid4()}", headers=auth_header(rsa_keypair, ["logs:read"])
    )
    body = resp.json()
    assert body["source"] == "fallback"
    assert "no recent error logs" in body["root_cause_summary"].lower()


# --- Caching ---


async def test_repeated_analysis_is_cached(client, rsa_keypair):
    set_llm_mode("success")
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id, message="same error every time")

    first = await client.get(f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"]))
    assert first.json()["cached"] is False

    # Change LLM mode — if the cache weren't hit, this call would now fail
    # over to the fallback path and produce a DIFFERENT source/summary.
    set_llm_mode("timeout")
    second = await client.get(f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"]))
    assert second.json()["cached"] is True
    assert second.json()["root_cause_summary"] == first.json()["root_cause_summary"]


async def test_different_services_do_not_share_cache(client, rsa_keypair):
    set_llm_mode("success")
    service_a = uuid.uuid4()
    service_b = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_a, message="error for A")
    await _ingest_error_log(client, rsa_keypair, service_b, message="error for B")

    await client.get(f"/api/v1/genai/analyze/{service_a}", headers=auth_header(rsa_keypair, ["logs:read"]))
    resp_b = await client.get(f"/api/v1/genai/analyze/{service_b}", headers=auth_header(rsa_keypair, ["logs:read"]))
    assert resp_b.json()["cached"] is False


# --- Persistence / history ---


async def test_analysis_persisted_and_appears_in_history(client, rsa_keypair):
    service_id = uuid.uuid4()
    await _ingest_error_log(client, rsa_keypair, service_id)
    analyze_resp = await client.get(f"/api/v1/genai/analyze/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"]))

    history_resp = await client.get(f"/api/v1/genai/history/{service_id}", headers=auth_header(rsa_keypair, ["logs:read"]))
    history = history_resp.json()
    assert len(history) == 1
    assert history[0]["root_cause_summary"] == analyze_resp.json()["root_cause_summary"]
