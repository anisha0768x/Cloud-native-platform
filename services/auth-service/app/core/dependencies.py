"""
Dependency injection wiring: composes repositories + settings into an
AuthService per-request. Keeping this in one place (rather than
constructing AuthService inline in each route) means the construction
logic changes in exactly one spot if we ever add a new dependency (e.g. an
email-verification sender).
"""

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.exceptions import UnauthorizedError
from platform_common.security import TokenPayload, decode_and_verify

from app.core.config import AuthServiceSettings
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService


def get_settings(request: Request) -> AuthServiceSettings:
    return request.app.state.settings


async def get_db_session(request: Request) -> AsyncSession:
    async with request.app.state.db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_user_repository(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    return UserRepository(session)


def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    settings: AuthServiceSettings = Depends(get_settings),
) -> AuthService:
    return AuthService(
        user_repo=UserRepository(session),
        refresh_repo=RefreshTokenRepository(session),
        jwt_private_key=settings.JWT_PRIVATE_KEY,
        access_token_expire_seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        refresh_token_expire_seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        max_failed_login_attempts=settings.MAX_FAILED_LOGIN_ATTEMPTS,
        failed_login_lockout_seconds=settings.FAILED_LOGIN_LOCKOUT_SECONDS,
    )


def get_current_user_token(
    request: Request,
    authorization: str = Header(default=""),
) -> TokenPayload:
    """
    Auth Service verifying its OWN issued tokens (used by GET /me). Every
    OTHER service does this same check against Auth Service's PUBLIC key
    only — this is the one service that also holds the private key, but
    verification here uses the same public-key path as everywhere else,
    proving the public key alone is sufficient (no special-casing).
    """
    settings: AuthServiceSettings = request.app.state.settings
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    return decode_and_verify(token, public_key=settings.JWT_PUBLIC_KEY)
