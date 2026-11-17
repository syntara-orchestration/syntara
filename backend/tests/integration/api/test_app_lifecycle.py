"""Integration tests for application lifecycle - audit system startup and shutdown."""

import logging
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app, lifespan
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.logging import AUDIT_LOGGER_NAME
from syntara.audit.outbox import session as outbox_session
from syntara.audit.outbox import worker as outbox_worker
from syntara.audit.outbox.session import AuditWorkerAsyncSessionLocal
from syntara.authz import resource_actions
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.logging import lifecycle as logging_lifecycle
from syntara.core.logging.logging import _UVICORN_LOGGER_NAMES
from syntara.settings.cache import settings_cache as settings_cache_module

_RegistryState = tuple[dict[str, list[str]] | None, frozenset[str], frozenset[str]]
"""Snapshot of the process-global resource-actions registry holder."""

_seeded_databases: set[str] = set()
"""Database URLs already seeded by _test_lifespan_context.

Keyed by URL rather than object identity so the guard holds even if the
engine fixture's scope or lifetime ever changes; seeding is also per
database, not per lifespan entry.
"""


def _snapshot_resource_actions() -> _RegistryState:
    """Capture the process-global resource-actions registry state."""
    return (
        resource_actions._registry,
        resource_actions._all_pairs,
        resource_actions._project_eligible,
    )


def _restore_resource_actions(state: _RegistryState) -> None:
    """Reinstall a captured resource-actions registry state."""
    (
        resource_actions._registry,
        resource_actions._all_pairs,
        resource_actions._project_eligible,
    ) = state


@pytest.fixture(autouse=True)
def _preserve_logging_state() -> Iterator[None]:
    """Restore logging handlers stripped by the lifespan shutdown.

    ``_lifespan_shutdown`` calls ``stop_loggers()``, which removes every root
    and audit logger handler — including the per-worker FileHandler installed
    by the session app fixture — and marks logging unconfigured so the next
    startup reconfigures it from scratch. Without this restore, every later
    test on the same xdist worker silently loses its app log capture.

    Startup also applies the runtime log level to the uvicorn loggers via
    ``_set_log_level``; those named levels are restored too.
    """
    root_logger = logging.getLogger()
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    saved_root_handlers = list(root_logger.handlers)
    saved_root_level = root_logger.level
    saved_audit_handlers = list(audit_logger.handlers)
    saved_audit_level = audit_logger.level
    saved_uvicorn_levels = {name: logging.getLogger(name).level for name in _UVICORN_LOGGER_NAMES}
    saved_state = logging_lifecycle._logging_state

    yield

    root_logger.handlers[:] = saved_root_handlers
    root_logger.setLevel(saved_root_level)
    audit_logger.handlers[:] = saved_audit_handlers
    audit_logger.setLevel(saved_audit_level)
    for name, level in saved_uvicorn_levels.items():
        logging.getLogger(name).setLevel(level)
    logging_lifecycle._logging_state = saved_state


@asynccontextmanager
async def _test_lifespan_context(test_db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Run the app lifespan with test database properly configured.

    The lifespan runs on a throwaway FastAPI instance. Re-entering it on the
    shared module-level app re-registered every router mid-session; with
    FastAPI >= 0.162 the re-included routes stopped honouring
    ``dependency_overrides[get_authz_evaluator]``, so list endpoints in later
    tests on the same xdist worker evaluated the real Rego policy instead of
    the conftest evaluator mock and returned empty results for users without
    role assignments.

    Router (re-)registration is stubbed out and the process globals the
    startup still writes (resource-actions registry, runtime settings cache)
    are snapshotted and restored, so nothing leaks to later tests on the
    worker.

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
        patch("syntara.audit.outbox.worker.AsyncSessionLocal", test_session_factory),
        patch("syntara.audit.outbox.worker.AuditWorkerAsyncSessionLocal", test_session_factory),
        patch("syntara.audit.outbox.session.AuditWorkerAsyncSessionLocal", test_session_factory),
        patch("syntara.api.main.RegoEvaluator", return_value=mock_evaluator),
        # Never (re-)register routers from the lifespan: the domain routers are
        # module-level singletons shared with every other test. Including them
        # here while the api-conftest evaluator monkeypatch is active leaves
        # route dispatch state that bypasses dependency_overrides in later
        # tests on the same worker. session_app already registered them once.
        patch("syntara.api.main.discover_and_register_routers", return_value=[]),
        patch("syntara.api.main.build_websocket_router", return_value=APIRouter()),
    ):
        # Seed required data before app startup (once per database: the
        # lifecycle tests do not restore the template database between
        # entries, so repeated seeding is redundant work).
        if str(test_db_engine.url) not in _seeded_databases:
            from syntara.core.seed import run_seeders

            await run_seeders(test_session_factory)
            _seeded_databases.add(str(test_db_engine.url))

        # Run the lifespan on a throwaway app so router (re-)registration and
        # app.state writes stay away from the app shared with other tests.
        lifespan_app = FastAPI(lifespan=lifespan)
        saved_route_count = len(app.routes)
        saved_registry = _snapshot_resource_actions()
        saved_runtime_settings = settings_cache_module._runtime_settings
        try:
            async with lifespan_app.router.lifespan_context(lifespan_app):
                # In-body guard: startup must not touch the shared app's
                # route table. The patches above neutralise the two known
                # registration paths; this catches any new path the moment
                # it happens rather than after the fact.
                assert len(app.routes) == saved_route_count, (
                    "app lifespan must not (de)register routes on the shared app"
                )
                yield
        finally:
            # Startup writes three process globals that the throwaway app
            # cannot contain; restore each so later tests on this worker see
            # the pre-startup state:
            #
            # - build_resource_actions() installs a near-empty registry
            #   (project_eligible shrinks to {"project"}), degrading policy
            #   validation and the project_eligible filter.
            # - set_runtime_settings() replaces the global settings cache
            #   with one whose watcher the shutdown then stops.
            _restore_resource_actions(saved_registry)
            settings_cache_module._runtime_settings = saved_runtime_settings

        # Post-restore guards: these verify the restores above ran and held.
        # They are intentionally after the finally block — their job is to
        # fail loudly if a future refactor drops or weakens a restore, not
        # to re-detect the (known) in-startup writes.
        assert _snapshot_resource_actions() == saved_registry, (
            "resource-actions registry must be restored after the lifespan"
        )
        assert settings_cache_module._runtime_settings is saved_runtime_settings, (
            "runtime settings cache must be restored after the lifespan"
        )
        assert len(app.routes) == saved_route_count, "app lifespan must not (de)register routes on the shared app"


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


@pytest.mark.asyncio
async def test_lifespan_context_redirects_outbox_worker_factories(test_db_engine: AsyncEngine) -> None:
    """Verify _test_lifespan_context redirects every factory the outbox worker reads.

    Regression guard for the deterministic Integration CI failures seen in
    October 2026: this context historically omitted
    syntara.audit.outbox.worker.AsyncSessionLocal, so when this file ran
    before a worker's first session_app test, the lru_cache singleton behind
    get_outbox_worker() was created bound to the real database factories
    (localhost:5432, unreachable in CI) and every later audit write in that
    pytest-xdist worker failed after retries.
    """
    async with _test_lifespan_context(test_db_engine):
        # The dot access below needs Any-typed module aliases: worker.py and
        # session.py only import these factory names, so mypy
        # --no-implicit-reexport flags reading them as module attributes.
        worker_ns: Any = outbox_worker
        session_ns: Any = outbox_session
        assert worker_ns.AsyncSessionLocal is not AsyncSessionLocal, (
            "_test_lifespan_context must patch syntara.audit.outbox.worker.AsyncSessionLocal "
            "(the outbox write factory); otherwise get_outbox_worker() caches a singleton "
            "bound to the real database"
        )
        assert worker_ns.AuditWorkerAsyncSessionLocal is not AuditWorkerAsyncSessionLocal, (
            "_test_lifespan_context must patch syntara.audit.outbox.worker.AuditWorkerAsyncSessionLocal"
        )
        assert session_ns.AuditWorkerAsyncSessionLocal is not AuditWorkerAsyncSessionLocal, (
            "_test_lifespan_context must patch syntara.audit.outbox.session.AuditWorkerAsyncSessionLocal"
        )
