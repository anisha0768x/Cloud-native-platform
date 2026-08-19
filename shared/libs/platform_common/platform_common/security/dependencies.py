"""
FastAPI dependencies for authentication and RBAC, reused by every service.

WHY here and not per-service: this is the SECOND enforcement layer
described in the security architecture (§10 of the master design) — the
API Gateway does a coarse check, but each service independently re-verifies
the token and checks fine-grained permissions before executing business
logic. Sharing this dependency guarantees that check is implemented
identically (and correctly) in all 12 services rather than re-written,
and possibly re-broken, 12 times.

DESIGN NOTE (post-Module-4 correction): the original version of this file
built the current-token dependency via a factory closing over a public key
captured at import/app-creation time, and had `require_permission` rely on
FastAPI's bare `Depends()` shortcut to source a `TokenPayload` — which
does NOT work, because FastAPI would try to construct `TokenPayload`
itself from request data rather than reuse an already-verified instance.
This went uncaught because no service actually exercised `require_permission`
until this module. Fixed here: `get_current_token` reads the service's
settings from `request.app.state.settings` at REQUEST time (matching the
pattern already used across Auth Service, API Gateway, and Monitoring
Service), and `require_permission` explicitly depends on it.
"""

from fastapi import Depends, Header, Request

from platform_common.exceptions import ForbiddenError, UnauthorizedError
from platform_common.security.jwt import TokenPayload, decode_and_verify


def get_current_token(request: Request, authorization: str = Header(default="")) -> TokenPayload:
    """
    Every service that stores its Settings instance at `app.state.settings`
    (all of them, by convention — see each service's main.py) gets a
    working current-token dependency for free via this function. Assumes
    `settings.JWT_PUBLIC_KEY` is populated (BaseServiceSettings subclasses
    that verify tokens all define this field).
    """
    settings = request.app.state.settings
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    return decode_and_verify(token, public_key=settings.JWT_PUBLIC_KEY)


def require_permission(permission: str):
    """
    Usage in a router:

        @router.post("/services", dependencies=[Depends(require_permission("service:create"))])

    or to also get the token payload in the handler:

        async def create(..., token: TokenPayload = Depends(require_permission("service:create"))):
    """

    def _check(token: TokenPayload = Depends(get_current_token)) -> TokenPayload:
        if permission not in token.permissions and "admin:*" not in token.permissions:
            raise ForbiddenError(f"Missing required permission: {permission}")
        return token

    return _check

