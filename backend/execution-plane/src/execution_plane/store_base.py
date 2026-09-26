"""Shared database resource lifecycle for execution-plane stores."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Self

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from execution_plane.store_errors import StoreConfigurationError, StoreSessionError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.pool import Pool


class StoreBase:
    """Own or borrow the database resources used by a concrete Store."""

    def __init__(
        self,
        database_url: str | None = None,
        poolclass: type[Pool] | None = None,
        *,
        engine: AsyncEngine | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        """Create a store backed by a borrowed session, URL, or engine."""
        self._session = session
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._engine: AsyncEngine | None = None
        self._owns_engine = False

        if session is not None:
            return
        if engine is not None:
            self._engine = engine
        else:
            if database_url is None:
                raise StoreConfigurationError
            self._engine = (
                create_async_engine(database_url)
                if poolclass is None
                else create_async_engine(database_url, poolclass=poolclass)
            )
            self._owns_engine = True

        self._session_factory = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)

    @classmethod
    def from_session(cls, session: AsyncSession) -> Self:
        """Create a store borrowing a request-scoped session."""
        return cls(session=session)

    @classmethod
    def from_engine(cls, engine: AsyncEngine) -> Self:
        """Create a store borrowing an application-owned engine."""
        return cls(engine=engine)

    @classmethod
    def from_database_url(cls, database_url: str, poolclass: type[Pool] | None = None) -> Self:
        """Create a store that owns an engine created from a database URL."""
        return cls(database_url, poolclass=poolclass)

    async def __aenter__(self) -> Self:
        """Return this store for use as an async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Dispose the store's database engine."""
        await self.close()

    async def close(self) -> None:
        """Dispose all pooled database connections owned by the store."""
        if self._owns_engine and self._engine is not None:
            await self._engine.dispose()

    @asynccontextmanager
    async def _session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a borrowed request session or an owned short-lived session."""
        if self._session is not None:
            yield self._session
            return
        if self._session_factory is None:
            raise StoreSessionError
        async with self._session_factory() as session:
            yield session
