"""Integration tests for seed_builtin_workflows' concurrency contract.

Backs the operational contract stated in ``seed_builtin.py``'s docstring:
re-runs are idempotent and concurrent invocations (deployment hook plus
several API replicas starting together) converge to the same state.

Test coverage:
- Two seed passes racing on an empty database leave exactly one workflow
  and one version per built-in definition. The create race is guarded by
  the ``uq_workflows_name_project`` unique constraint: the loser's
  IntegrityError rolls back per definition and its pass continues cleanly.
- A sequential unchanged re-run creates no new versions or publish events.
- Two re-runs racing after a definition change leave exactly one new
  version per workflow. The update race is guarded by the unique index on
  ``(workflow_id, version)``; the loser's partial writes (new version row
  plus the workflow row update) are rolled back together.

No live Temporal server is required — the Schedule side of the contract
(create-or-update convergence) is covered by ScheduledTriggerService's own
tests; the service is patched here to keep the focus on database-level
convergence.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import col, select

from syntara.authz.seed import seed_authz_data
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.seed_builtin import _BUILTIN_DEFINITIONS, seed_builtin_workflows

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def _mock_scheduled_trigger_service() -> Generator[MagicMock, None, None]:
    """Patch the Temporal sync out of these DB-convergence tests (module docstring)."""
    with patch("syntara.workflows.seed_builtin.ScheduledTriggerService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.sync_scheduled_triggers = AsyncMock(return_value=0)
        mock_cls.return_value = mock_instance
        yield mock_instance


async def _seed_concurrently(factory: async_sessionmaker[AsyncSession], passes: int) -> None:
    """Run ``passes`` seed invocations concurrently, each on its own session."""
    sessions = [factory() for _ in range(passes)]
    try:
        await asyncio.gather(*(seed_builtin_workflows(session) for session in sessions))
    finally:
        for session in sessions:
            await session.close()


async def _fetch_builtin_state(
    factory: async_sessionmaker[AsyncSession],
) -> dict[str, tuple[Workflow, list[WorkflowVersion], int]]:
    """Read built-ins as ``{name: (workflow, versions sorted, publish_event_count)}``."""
    session = factory()
    try:
        workflows = (
            await session.exec(select(Workflow).where(col(Workflow.is_builtin) == True))  # noqa: E712
        ).all()
        state: dict[str, tuple[Workflow, list[WorkflowVersion], int]] = {}
        for workflow in workflows:
            versions = (
                await session.exec(
                    select(WorkflowVersion)
                    .where(col(WorkflowVersion.workflow_id) == workflow.id)
                    .order_by(col(WorkflowVersion.version))
                )
            ).all()
            events = (
                await session.exec(
                    select(WorkflowPublishEvent.id).where(col(WorkflowPublishEvent.workflow_id) == workflow.id)
                )
            ).all()
            state[workflow.name] = (workflow, list(versions), len(events))
        return state
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_first_seed_converges_and_rerun_is_idempotent(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two concurrent first passes converge; an unchanged re-run is a no-op."""
    await seed_authz_data(test_db_session)

    await _seed_concurrently(test_db_session_factory, passes=2)

    state = await _fetch_builtin_state(test_db_session_factory)
    expected_names = {d["name"] for d in _BUILTIN_DEFINITIONS}
    assert set(state) == expected_names
    for name, (workflow, versions, events) in state.items():
        assert [v.version for v in versions] == [1], name
        assert workflow.current_version == 1, name
        assert workflow.published_version_id == versions[0].id, name
        assert events == 1, name

    # Sequential unchanged re-run: no new versions, no new publish events.
    rerun_session = test_db_session_factory()
    try:
        await seed_builtin_workflows(rerun_session)
    finally:
        await rerun_session.close()

    state_after_rerun = await _fetch_builtin_state(test_db_session_factory)
    for name, (workflow, versions, events) in state_after_rerun.items():
        assert [v.version for v in versions] == [1], name
        assert workflow.current_version == 1, name
        assert events == 1, name


@pytest.mark.asyncio
async def test_concurrent_rerun_of_changed_definition_converges(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two concurrent re-runs after a definition change leave one new version.

    Both racers read ``current_version == 1`` and try to create version 2;
    the ``(workflow_id, version)`` unique index rejects the loser, whose
    per-definition rollback discards its version row and workflow update
    together, so the pass converges instead of duplicating versions.
    """
    await seed_authz_data(test_db_session)

    initial_session = test_db_session_factory()
    try:
        await seed_builtin_workflows(initial_session)
    finally:
        await initial_session.close()

    changed = [{**d, "description": f"{d['description']} (changed)"} for d in _BUILTIN_DEFINITIONS]
    changed_descriptions = {d["name"]: d["description"] for d in changed}
    with patch("syntara.workflows.seed_builtin._BUILTIN_DEFINITIONS", changed):
        await _seed_concurrently(test_db_session_factory, passes=2)

    state = await _fetch_builtin_state(test_db_session_factory)
    for name, (workflow, versions, events) in state.items():
        assert [v.version for v in versions] == [1, 2], name
        assert workflow.current_version == 2, name
        assert workflow.published_version_id == versions[1].id, name
        assert workflow.description == changed_descriptions[name], name
        assert events == 2, name
