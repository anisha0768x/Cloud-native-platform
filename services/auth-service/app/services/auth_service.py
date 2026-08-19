"""
AuthService: all business rules live here, deliberately kept independent
of FastAPI (no Request/Response objects, no HTTP status codes) so it can
be unit tested directly and reused by a future CLI/admin tool without any
HTTP layer involved.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from platform_common.exceptions import ConflictError, UnauthorizedError
from platform_common.security import encode_token, hash_password, verify_password

from app.models.auth import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse, UserResponse


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        *,
        jwt_private_key: str,
        access_token_expire_seconds: int,
        refresh_token_expire_seconds: int,
        max_failed_login_attempts: int,
        failed_login_lockout_seconds: int,
    ):
        self._users = user_repo
        self._refresh_tokens = refresh_repo
        self._private_key = jwt_private_key
        self._access_ttl = access_token_expire_seconds
        self._refresh_ttl = refresh_token_expire_seconds
        self._max_failed_attempts = max_failed_login_attempts
        self._lockout_seconds = failed_login_lockout_seconds

    async def register(self, *, email: str, password: str, full_name: str | None) -> User:
        existing = await self._users.get_by_email(email)
        if existing:
            raise ConflictError("An account with this email already exists")

        user = await self._users.create(
            email=email, password_hash=hash_password(password), full_name=full_name
        )
        await self._users.assign_default_role(user, role_name="viewer")
        return user

    async def login(self, *, email: str, password: str) -> tuple[User, TokenResponse]:
        user = await self._users.get_by_email(email)

        # Deliberately identical error message/timing-shape for "no such user"
        # and "wrong password" — distinguishing them lets an attacker
        # enumerate valid emails, which is a real (if minor) info leak.
        if user is None:
            raise UnauthorizedError("Invalid email or password")

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise UnauthorizedError(
                "Account temporarily locked due to repeated failed login attempts",
                details={"locked_until": user.locked_until.isoformat()},
            )

        if not verify_password(password, user.password_hash):
            lockout_until = None
            if user.failed_login_attempts + 1 >= self._max_failed_attempts:
                lockout_until = datetime.now(timezone.utc) + timedelta(seconds=self._lockout_seconds)
            await self._users.record_failed_login(
                user, max_attempts=self._max_failed_attempts, lockout_until=lockout_until
            )
            raise UnauthorizedError("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedError("Account is deactivated")

        await self._users.reset_failed_login(user)
        tokens = await self._issue_tokens(user)
        return user, tokens

    async def refresh(self, *, raw_refresh_token: str) -> TokenResponse:
        record = await self._refresh_tokens.get_valid(raw_refresh_token)
        if record is None or record.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("Refresh token is invalid or expired")

        user = await self._users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Account no longer active")

        # Rotate: revoke the used refresh token and issue a brand new pair.
        # Rotation means a stolen-but-unused refresh token becomes useless
        # the moment the legitimate user's client refreshes again — it
        # limits the blast radius of a leaked token to a single use.
        await self._refresh_tokens.revoke(record)
        return await self._issue_tokens(user)

    async def logout(self, *, raw_refresh_token: str) -> None:
        record = await self._refresh_tokens.get_valid(raw_refresh_token)
        if record:
            await self._refresh_tokens.revoke(record)

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access_token = encode_token(
            private_key=self._private_key,
            subject=str(user.id),
            roles=user.role_names(),
            permissions=user.permission_names(),
            expires_in_seconds=self._access_ttl,
        )
        raw_refresh_token = secrets.token_urlsafe(48)
        await self._refresh_tokens.store(
            user_id=user.id,
            raw_token=raw_refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._refresh_ttl),
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=self._access_ttl,
        )

    @staticmethod
    def to_user_response(user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            roles=user.role_names(),
            permissions=user.permission_names(),
        )
