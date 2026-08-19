"""
Gateway-level auth: a COARSE check only.

This deliberately does NOT do fine-grained permission checks (that's each
service's job via platform_common's `require_permission`, per the
defense-in-depth design in the master architecture doc, §10). The
gateway's job is narrower and cheaper: reject requests with no token, a
malformed token, or an expired/tampered signature BEFORE they consume a
backend service's CPU/DB connection — a backend never even sees garbage
auth headers.

Because this is a second, independent verification (not the source of
truth), a failure here does not prevent the backend from independently
re-checking — it's pure defense in depth, so a bug in this file fails
closed (unauthenticated requests get rejected here or later) rather than
failing open.
"""

from fastapi import Request

from platform_common.exceptions import UnauthorizedError
from platform_common.security import TokenPayload, decode_and_verify

from app.core.config import GatewaySettings


def is_public_path(path: str, public_prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefix) for prefix in public_prefixes)


def authenticate_request(request: Request, settings: GatewaySettings) -> TokenPayload | None:
    """
    Returns the verified token payload, or None if the path is public and
    no token was supplied. Raises UnauthorizedError for anything else that
    doesn't check out.
    """
    path = request.url.path
    authorization = request.headers.get("authorization", "")

    if not authorization:
        if is_public_path(path, settings.PUBLIC_PATH_PREFIXES):
            return None
        raise UnauthorizedError("Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    return decode_and_verify(token, public_key=settings.JWT_PUBLIC_KEY)


def resolve_rate_limit_key(request: Request, token: TokenPayload | None) -> str:
    """
    Prefer the authenticated user's id (fair, personal budget); fall back
    to client IP for anonymous requests (login/register still need a
    limit, or they become an open brute-force/spam surface).
    """
    if token is not None:
        return f"user:{token.sub}"
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"
