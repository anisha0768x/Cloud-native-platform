"""
JWT verification (shared) + issuing (Auth Service only).

WHY asymmetric (RS256) signing instead of a shared HS256 secret:
  With HS256, every service that needs to *verify* a token would also hold
  the secret capable of *issuing* forged tokens — any one of the 12
  services being compromised would mean full platform impersonation.
  With RS256, only the Auth Service holds the private key; every other
  service holds only the public key and can verify but never mint tokens.
  This is a direct, deliberate security-architecture decision (defense in
  depth), not just a library default.

This module provides `decode_and_verify` for use by every service, and
`encode_token` which only the Auth Service actually calls (it's the only
service configured with a private key).
"""

import time
import uuid
from typing import Any

import jwt
from jwt import InvalidTokenError

from platform_common.exceptions import UnauthorizedError

ALGORITHM = "RS256"


class TokenPayload:
    def __init__(self, sub: str, roles: list[str], permissions: list[str], exp: int, raw: dict[str, Any]):
        self.sub = sub  # user id
        self.roles = roles
        self.permissions = permissions
        self.exp = exp
        self.raw = raw


def encode_token(
    *,
    private_key: str,
    subject: str,
    roles: list[str],
    permissions: list[str],
    expires_in_seconds: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Called only by Auth Service, which is the sole holder of the private key."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "roles": roles,
        "permissions": permissions,
        "iat": now,
        "exp": now + expires_in_seconds,
        # Unique per token: without this, two tokens issued for the same
        # user within the same second (e.g. immediate login-then-refresh)
        # would be byte-for-byte identical, which surfaced as a genuine
        # test failure while building this service.
        "jti": uuid.uuid4().hex,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, private_key, algorithm=ALGORITHM)


def decode_and_verify(token: str, *, public_key: str) -> TokenPayload:
    """
    Called by every service to verify a token presented in an
    `Authorization: Bearer <token>` header. Raises UnauthorizedError
    (platform-standard exception, see exceptions/errors.py) on any
    failure so the FastAPI handler doesn't need its own try/except.
    """
    try:
        raw = jwt.decode(token, public_key, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token", details={"reason": str(exc)}) from exc

    return TokenPayload(
        sub=raw["sub"],
        roles=raw.get("roles", []),
        permissions=raw.get("permissions", []),
        exp=raw["exp"],
        raw=raw,
    )
