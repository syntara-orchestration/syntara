"""Integration tests for application lifecycle - audit system startup and shutdown."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.audit.dispatcher import AuditEventDispatcher


@asynccontextmanager
async def _test_lifespan_context(test_db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Run the app lifespan with test database properly configured.

    Args:
        test_db_engine: Test database engine with migrations applied

    """
    # Create test session factory from the test database engine
    test_session_factory = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)

    # Mock authz evaluator so the lifespan health check passes
    mock_evaluator = AsyncMock()
    mock_evaluator.health = AsyncMock(return_value=True)
    mock_evaluator.start = MagicMock()
    mock_evaluator.stop = AsyncMock()
    mock_evaluator.evaluate = MagicMock(return_value={"allow": True})

    # Patch all database connections to use the test database
    # This ensures _check_settings_catalog() and other startup code use the migrated test DB
    with (
        patch("syntara.core.database.session.engine", test_db_engine),
        patch("syntara.core.database.session.AsyncSessionLocal", test_session_factory),
        patch("syntara.api.main.engine", test_db_engine),
        patch("syntara.api.main.AsyncSessionLocal", test_session_factory),
        patch("syntara.audit.outbox.worker.AuditWorkerAsyncSessionLocal", test_session_factory),
        patch("syntara.api.main.RegoEvaluator", return_value=mock_evaluator),
    ):
        # Seed required data before app startup
        from syntara.core.seed import run_seeders

        await run_seeders(test_session_factory)

        # Run the app lifespan
        async with app.router.lifespan_context(app):
            yield


@pytest.mark.asyncio
async def test_audit_dispatcher_registers_handlers_on_startup(test_db_engine: AsyncEngine) -> None:
    """Verify that audit handlers are discovered and registered during app startup (I0).

    This test ensures that the dispatcher bootstrap in main.py successfully:
    1. Discovers handlers from syntara.auth.audit
    2. Registers them with AuditEventDispatcher
    3. Results in a non-empty registry after startup
    """
    # Clear any pre-existing state
    AuditEventDispatcher._reset()
    assert len(AuditEventDispatcher._registry) == 0

    # Run the lifespan - startup should discover and register handlers
    async with _test_lifespan_context(test_db_engine):
        # Verify handlers were registered
        assert len(AuditEventDispatcher._registry) > 0, (
            "Expected audit handlers to be registered during startup, but registry is empty"
        )


@pytest.mark.asyncio
async def test_multiple_startup_shutdown_cycles_do_not_accumulate_handlers(test_db_engine: AsyncEngine) -> None:
    """Verify that multiple startup/shutdown cycles don't accumulate handlers (I1).

    This test ensures that handlers are properly cleaned up between cycles
    and don't leak across test sessions or app restarts.
    """
    # Clear any pre-existing state
    AuditEventDispatcher._reset()

    # First cycle
    async with _test_lifespan_context(test_db_engine):
        first_count = len(AuditEventDispatcher._registry)
        assert first_count > 0

    # Second cycle - should register the same number of handlers
    async with _test_lifespan_context(test_db_engine):
        second_count = len(AuditEventDispatcher._registry)
        assert second_count == first_count, (
            f"Expected {first_count} handlers in second cycle, but got {second_count}. "
            "Handlers may be accumulating across cycles."
        )
