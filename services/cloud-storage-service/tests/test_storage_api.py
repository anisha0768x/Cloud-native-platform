import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


def auth_header(rsa_keypair, permissions):
    return {"Authorization": f"Bearer {make_token(rsa_keypair, permissions=permissions)}"}


async def test_upload_requires_permission(client, rsa_keypair):
    resp = await client.put(
        "/api/v1/storage/objects/reports/q1.csv",
        files={"file": ("q1.csv", b"a,b\n1,2\n", "text/csv")},
        headers=auth_header(rsa_keypair, ["storage:read"]),
    )
    assert resp.status_code == 403


async def test_upload_and_download_roundtrip(client, rsa_keypair):
    upload_resp = await client.put(
        "/api/v1/storage/objects/reports/q1.csv",
        files={"file": ("q1.csv", b"a,b\n1,2\n", "text/csv")},
        headers=auth_header(rsa_keypair, ["storage:write"]),
    )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["key"] == "reports/q1.csv"
    assert upload_resp.json()["size_bytes"] == 8

    download_resp = await client.get(
        "/api/v1/storage/objects/reports/q1.csv", headers=auth_header(rsa_keypair, ["storage:read"])
    )
    assert download_resp.status_code == 200
    assert download_resp.content == b"a,b\n1,2\n"


async def test_download_nonexistent_key_returns_404(client, rsa_keypair):
    resp = await client.get(
        "/api/v1/storage/objects/does/not/exist.txt", headers=auth_header(rsa_keypair, ["storage:read"])
    )
    assert resp.status_code == 404


async def test_upload_rejects_path_traversal_key(client, rsa_keypair):
    resp = await client.put(
        "/api/v1/storage/objects/../../etc/passwd",
        files={"file": ("x.txt", b"data", "text/plain")},
        headers=auth_header(rsa_keypair, ["storage:write"]),
    )
    # FastAPI's :path converter normalizes ../ before it even reaches our
    # handler in some cases; either a 404 (route didn't match) or a 422
    # (validate_key rejected it) is an acceptable "did not silently
    # succeed" outcome here.
    assert resp.status_code in (404, 422)


async def test_upload_rejects_oversized_file(client, rsa_keypair):
    oversized = b"x" * 2000  # exceeds the test settings' 1024-byte MAX_UPLOAD_SIZE_BYTES
    resp = await client.put(
        "/api/v1/storage/objects/big-file.bin",
        files={"file": ("big.bin", oversized, "application/octet-stream")},
        headers=auth_header(rsa_keypair, ["storage:write"]),
    )
    assert resp.status_code == 422


async def test_delete_removes_object(client, rsa_keypair):
    await client.put(
        "/api/v1/storage/objects/temp/delete-me.txt",
        files={"file": ("x.txt", b"temp", "text/plain")},
        headers=auth_header(rsa_keypair, ["storage:write"]),
    )
    delete_resp = await client.delete(
        "/api/v1/storage/objects/temp/delete-me.txt", headers=auth_header(rsa_keypair, ["storage:write"])
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get(
        "/api/v1/storage/objects/temp/delete-me.txt", headers=auth_header(rsa_keypair, ["storage:read"])
    )
    assert get_resp.status_code == 404


async def test_list_objects_filters_by_prefix(client, rsa_keypair):
    write_headers = auth_header(rsa_keypair, ["storage:write"])
    await client.put("/api/v1/storage/objects/logs/a.log", files={"file": ("a.log", b"a", "text/plain")}, headers=write_headers)
    await client.put("/api/v1/storage/objects/logs/b.log", files={"file": ("b.log", b"b", "text/plain")}, headers=write_headers)
    await client.put("/api/v1/storage/objects/reports/r.csv", files={"file": ("r.csv", b"c", "text/csv")}, headers=write_headers)

    resp = await client.get(
        "/api/v1/storage/objects", params={"prefix": "logs/"}, headers=auth_header(rsa_keypair, ["storage:read"])
    )
    results = resp.json()
    assert len(results) == 2
    assert all(o["key"].startswith("logs/") for o in results)


async def test_presigned_url_endpoint(client, rsa_keypair):
    await client.put(
        "/api/v1/storage/objects/shared/report.pdf",
        files={"file": ("report.pdf", b"%PDF-fake", "application/pdf")},
        headers=auth_header(rsa_keypair, ["storage:write"]),
    )
    resp = await client.get(
        "/api/v1/storage/objects/shared/report.pdf/presigned-url", headers=auth_header(rsa_keypair, ["storage:read"])
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "shared/report.pdf"
    assert body["url"].startswith("http")
    assert body["expires_in_seconds"] > 0
