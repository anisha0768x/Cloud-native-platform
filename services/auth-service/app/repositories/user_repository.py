"""
Repository layer: pure data access. Contains no business rules (no
password checking, no token generation) — that belongs in the service
layer. This separation is what lets AuthService be unit-tested with a
fake/mock repository instead of a real database.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Role, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str, full_name: str | None) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name)
        self._session.add(user)
        await self._session.flush()  # populate user.id without committing yet
        return user

    async def assign_default_role(self, user: User, role_name: str = "viewer") -> None:
        result = await self._session.execute(select(Role).where(Role.name == role_name))
        role = result.scalar_one_or_none()
        if role:
            # Same reasoning as the RBAC seed script: force the async load
            # of the current (empty) collection through the session before
            # mutating it, rather than letting attribute access trigger an
            # implicit lazy load outside the greenlet context.
            await self._session.refresh(user, attribute_names=["roles"])
            user.roles.append(role)

    async def record_failed_login(self, user: User, *, max_attempts: int, lockout_until: datetime | None) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= max_attempts:
            user.locked_until = lockout_until
        await self._session.flush()

    async def reset_failed_login(self, user: User) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None
        await self._session.flush()
