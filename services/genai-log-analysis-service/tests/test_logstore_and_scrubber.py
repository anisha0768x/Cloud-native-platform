from datetime import datetime, timedelta, timezone

import pytest

from app.logstore.base import LogEntry
from app.logstore.in_memory import InMemoryLogStore
from app.services.scrubber import scrub

pytestmark = pytest.mark.asyncio


def test_scrub_redacts_email():
    assert "user@example.com" not in scrub("Failed login for user@example.com")
    assert "REDACTED_EMAIL" in scrub("Failed login for user@example.com")


def test_scrub_redacts_long_token():
    text = "Authorization failed with token test_token_abcdefghijklmnopqrstuvwxyz123456"
    result = scrub(text)
    assert "test_token_abcdefghijklmnopqrstuvwxyz123456" not in result
    assert "REDACTED_TOKEN" in result


def test_scrub_redacts_aws_key():
    text = "Using AWS key AKIAIOSFODNN7EXAMPLE for upload"
    result = scrub(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in result


def test_scrub_redacts_ipv4():
    text = "Connection refused from 192.168.1.100"
    result = scrub(text)
    assert "192.168.1.100" not in result
    assert "REDACTED_IPV4" in result


def test_scrub_preserves_normal_short_words():
    text = "Database connection timeout after retry"
    result = scrub(text)
    assert result == text  # nothing here should look like a secret


async def test_in_memory_store_search_filters_by_service_id():
    store = InMemoryLogStore()
    now = datetime.now(timezone.utc)
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="oops", timestamp=now))
    await store.index(LogEntry(service_id="svc-b", level="ERROR", message="oops", timestamp=now))

    results = await store.search(service_id="svc-a")
    assert len(results) == 1
    assert results[0].service_id == "svc-a"


async def test_in_memory_store_search_filters_by_level():
    store = InMemoryLogStore()
    now = datetime.now(timezone.utc)
    await store.index(LogEntry(service_id="svc-a", level="INFO", message="ok", timestamp=now))
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="bad", timestamp=now))

    results = await store.search(service_id="svc-a", level="ERROR")
    assert len(results) == 1
    assert results[0].level == "ERROR"


async def test_in_memory_store_search_filters_by_query_text():
    store = InMemoryLogStore()
    now = datetime.now(timezone.utc)
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="connection timeout", timestamp=now))
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="disk full", timestamp=now))

    results = await store.search(service_id="svc-a", query="timeout")
    assert len(results) == 1
    assert "timeout" in results[0].message


async def test_in_memory_store_returns_most_recent_first():
    store = InMemoryLogStore()
    now = datetime.now(timezone.utc)
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="first", timestamp=now - timedelta(minutes=10)))
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="second", timestamp=now))

    results = await store.search(service_id="svc-a")
    assert results[0].message == "second"


async def test_recent_errors_only_returns_error_level():
    store = InMemoryLogStore()
    now = datetime.now(timezone.utc)
    await store.index(LogEntry(service_id="svc-a", level="INFO", message="fine", timestamp=now))
    await store.index(LogEntry(service_id="svc-a", level="ERROR", message="broken", timestamp=now))

    results = await store.recent_errors(service_id="svc-a")
    assert len(results) == 1
    assert results[0].level == "ERROR"
