"""
WHY a real local SMTP server (via aiosmtpd) rather than mocking
aiosmtplib.send: the whole point of EmailChannel is that it constructs a
correct MIME message and successfully speaks SMTP — mocking the send call
away would leave that unverified. Same reasoning as every other module's
"real mock backend server" test pattern (API Gateway, Dashboard Service,
etc.), just applied to SMTP instead of HTTP.
"""

import asyncio
import threading
import time
import uuid

import httpx as sync_httpx
import pytest
import pytest_asyncio
import uvicorn
from aiosmtpd.controller import Controller
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.security import encode_token

from app.core.config import NotificationServiceSettings
from app.core.dependencies import get_db_session
from app.main import create_app

MOCK_WEBHOOK_PORT = 18801
MOCK_SLACK_PORT = 18802
SMTP_PORT = 18825

_received_webhooks: list[dict] = []
_received_slack: list[dict] = []
_webhook_should_fail = False


class _CapturingSmtpHandler:
    """aiosmtpd handler that records every message it receives."""

    def __init__(self):
        self.received: list[dict] = []

    async def handle_DATA(self, server, session, envelope):
        self.received.append(
            {
                "mail_from": envelope.mail_from,
                "rcpt_tos": envelope.rcpt_tos,
                "content": envelope.content.decode("utf-8", errors="replace"),
            }
        )
        return "250 Message accepted for delivery"


def _build_mock_webhook_app() -> FastAPI:
    mock = FastAPI()

    @mock.post("/webhook")
    async def webhook(request: Request):
        if _webhook_should_fail:
            return JSONResponse(status_code=500, content={"error": "simulated failure"})
        body = await request.json()
        _received_webhooks.append(body)
        return {"ok": True}

    return mock


def _build_mock_slack_app() -> FastAPI:
    mock = FastAPI()

    @mock.post("/slack")
    async def slack(request: Request):
        body = await request.json()
        _received_slack.append(body)
        return {"ok": True}

    return mock


def _run_server(app: FastAPI, port: int, path: str):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            sync_httpx.post(f"http://127.0.0.1:{port}{path}", json={}, timeout=0.3)
            break
        except Exception:
            time.sleep(0.1)
    return server


@pytest.fixture(scope="session")
def smtp_handler():
    return _CapturingSmtpHandler()


@pytest.fixture(scope="session")
def smtp_server(smtp_handler):
    controller = Controller(smtp_handler, hostname="127.0.0.1", port=SMTP_PORT)
    controller.start()
    yield controller
    controller.stop()


@pytest.fixture(scope="session")
def mock_backends():
    webhook_server = _run_server(_build_mock_webhook_app(), MOCK_WEBHOOK_PORT, "/webhook")
    slack_server = _run_server(_build_mock_slack_app(), MOCK_SLACK_PORT, "/slack")
    yield {
        "webhook_url": f"http://127.0.0.1:{MOCK_WEBHOOK_PORT}/webhook",
        "slack_url": f"http://127.0.0.1:{MOCK_SLACK_PORT}/slack",
    }
    webhook_server.should_exit = True
    slack_server.should_exit = True


@pytest.fixture(autouse=True)
def reset_captured_state():
    global _webhook_should_fail
    _received_webhooks.clear()
    _received_slack.clear()
    _webhook_should_fail = False
    yield
    _webhook_should_fail = False


def get_received_webhooks() -> list[dict]:
    return _received_webhooks


def get_received_slack() -> list[dict]:
    return _received_slack


def set_webhook_failing(value: bool):
    global _webhook_should_fail
    _webhook_should_fail = value


@pytest.fixture(scope="session")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def make_token(rsa_keypair, *, permissions: list[str]) -> str:
    private_key, _ = rsa_keypair
    return encode_token(
        private_key=private_key, subject=str(uuid.uuid4()), roles=["operator"],
        permissions=permissions, expires_in_seconds=3600,
    )


@pytest_asyncio.fixture
async def settings(mock_backends, smtp_server, rsa_keypair):
    _, public_key = rsa_keypair
    return NotificationServiceSettings(
        DATABASE_URL="postgresql+asyncpg://platform:platform_local_dev_only@localhost:5432/notification_service_test",
        JWT_PUBLIC_KEY=public_key,
        WEBHOOK_URL=mock_backends["webhook_url"],
        SLACK_WEBHOOK_URL=mock_backends["slack_url"],
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=SMTP_PORT,
        SMTP_FROM_ADDRESS="alerts@platform.test",
        SMTP_TO_ADDRESSES=["oncall@platform.test"],
        ESCALATION_WINDOW_MINUTES=15,
        ENABLE_ESCALATION_WORKER=False,
    )


@pytest_asyncio.fixture
async def db_session(settings):
    from platform_common.db import Database

    db = Database(settings.DATABASE_URL)
    async with db.engine.connect() as connection:
        trans = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await db.dispose()


@pytest_asyncio.fixture
async def client(settings, db_session):
    import httpx

    app = create_app()
    app.state.settings = settings
    app.state.http_client = httpx.AsyncClient()

    async def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await app.state.http_client.aclose()
