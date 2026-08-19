import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import RefreshToken


def hash_token(raw_token: str) -> str:
    # SHA-256 is fine here (not bcrypt): this isn't a low-entropy password,
    # it's a 256-bit random token — no risk of brute force, and we need a
    # fast deterministic hash to look it up by index on every refresh call.
    return hashlib.sha256(raw_token.encode()).hexdigest()


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def store(self, *, user_id: uuid.UUID, raw_token: str, expires_at: datetime) -> RefreshToken:
        record = RefreshToken(user_id=user_id, token_hash=hash_token(raw_token), expires_at=expires_at)
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_valid(self, raw_token: str) -> RefreshToken | None:
        token_hash = hash_token(raw_token)
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
        )
        return result.scalar_one_or_none()

    async def revoke(self, record: RefreshToken) -> None:
        record.revoked = True
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        )
        for record in result.scalars():
            record.revoked = True
        await self._session.flush()
