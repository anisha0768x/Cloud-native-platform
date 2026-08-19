"""
Async SQLAlchemy engine/session factory.

WHY shared: every relational-DB-backed service (Auth, Monitoring, Metrics
control tables, Notification, Cloud SQL, etc.) needs the identical
boilerplate — async engine, session factory, a FastAPI dependency that
yields a session and guarantees close/rollback. Centralizing it means a
connection-pool tuning fix or a bug fix here fixes it everywhere at once
instead of needing 8 separate patches.

Each service still owns its OWN database and its OWN models — this module
only provides the *mechanism* to connect, not the schema.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """
    Builds an async engine with pool settings suited to a service running
    multiple replicas behind K8s (small pool per pod; total DB connections
    = pool_size * replica_count, so we keep per-pod pools modest).
    """
    return create_async_engine(
        database_url,
        echo=echo,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # detects stale connections after DB failover
        pool_recycle=1800,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Database:
    """
    Thin wrapper a service instantiates once at startup:

        db = Database(settings.DATABASE_URL)
        app.state.db = db

    and uses `db.session_dependency` as a FastAPI `Depends(...)` target.
    """

    def __init__(self, database_url: str, *, echo: bool = False):
        self.engine = build_engine(database_url, echo=echo)
        self.session_factory = build_session_factory(self.engine)

    async def session_dependency(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """For use outside request handlers, e.g. Kafka consumers, CLI scripts."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def health_check(self) -> bool:
        from sqlalchemy import text

        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
