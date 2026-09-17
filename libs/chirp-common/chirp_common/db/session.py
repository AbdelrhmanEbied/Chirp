"""Async engine and session lifecycle.

One `Database` object per service, created at startup and closed at shutdown.
Handlers receive a session through FastAPI's dependency system; they never
create engines themselves.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from chirp_common.config import DatabaseSettings
from chirp_common.errors import DependencyError

log = logging.getLogger(__name__)


class Database:
    """Owns the engine and session factory for one service."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        connect_args: dict[str, object] = {}
        if settings.database_url.startswith("postgresql"):
            # Server-side statement timeout is the backstop for a query that
            # would otherwise hold a pooled connection open indefinitely.
            connect_args["server_settings"] = {
                "statement_timeout": str(settings.db_statement_timeout_ms),
                "application_name": settings.db_application_name,
            }
        engine_kwargs: dict[str, object] = {
            "echo": settings.db_echo,
            "connect_args": connect_args,
        }
        if settings.database_url.startswith("sqlite"):
            # SQLite is only used by the fast unit suite. Its async driver runs
            # on a non-queue pool, which rejects the sizing arguments below.
            # Behavioural differences from PostgreSQL are why the integration
            # suite points TEST_DATABASE_URL at a real PostgreSQL instance.
            engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs.update(
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout_seconds,
                pool_recycle=settings.db_pool_recycle_seconds,
                pool_pre_ping=True,
            )
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url, **engine_kwargs
        )
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, autoflush=False
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session, committing on success and rolling back on error."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def check(self) -> bool:
        """Readiness probe: can we actually reach the database right now?"""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except (SQLAlchemyError, DBAPIError, OSError) as exc:
            log.warning("database health check failed", extra={"error": str(exc)})
            return False

    async def dispose(self) -> None:
        await self._engine.dispose()


@asynccontextmanager
async def transactional(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Explicit transaction boundary for multi-statement writes.

    Use where a unit of work must be all-or-nothing and the outer
    request-scoped commit is too coarse.
    """
    try:
        async with session.begin_nested():
            yield session
    except SQLAlchemyError as exc:
        raise DependencyError("Database transaction failed.") from exc
