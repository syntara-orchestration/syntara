"""PostgreSQL durability and unchanged-rerun checks for built-in seeding."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlmodel import col, select

from syntara.authz.models.project import Project
from syntara.authz.seed import seed_authz_data
from syntara.core.seed_context import strict_mode_context_var
from syntara.workflows.exceptions import ScheduledTriggerSyncError
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.seed_builtin import _BUILTIN_DEFINITIONS, seed_builtin_workflows

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def mock_schedule_sync() -> Generator[AsyncMock, None, None]:
    """Keep Temporal external to the real-database seeding tests."""
    with patch("syntara.workflows.seed_builtin.ScheduledTriggerService") as service:
        sync = AsyncMock(return_value=0)
        service.return_value.sync_scheduled_triggers = sync
        yield sync


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True], ids=["first-seed", "definition-update"])
async def test_strict_sync_abort_preserves_committed_definitions(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    mock_schedule_sync: AsyncMock,
    *,
    existing: bool,
) -> None:
    """Fresh sessions see committed rows before sync and after a mid-batch abort."""
    await seed_authz_data(test_db_session)
    if existing:
        async with test_db_session_factory() as session:
            await seed_builtin_workflows(session)

    definitions = [{**d, "description": f"{d['description']} (release update)"} for d in _BUILTIN_DEFINITIONS]
    failing_name = "Integration Health Check"
    failure_index = next(i for i, d in enumerate(definitions) if d["name"] == failing_name)
    processed_names = {d["name"] for d in definitions[: failure_index + 1]}
    error = ScheduledTriggerSyncError("health-check", 1)

    async def sync(workflow_id: str, workflow_definition: dict[str, Any], *, is_builtin: bool) -> int:
        assert is_builtin
        # A separate connection must already see the published version at the
        # moment Temporal sync runs; a flush without a commit cannot satisfy this.
        async with test_db_session_factory() as reader:
            workflow = await reader.get(Workflow, UUID(workflow_id))
            assert workflow is not None
            assert workflow.current_version == (2 if existing else 1)
            version = await reader.get(WorkflowVersion, workflow.published_version_id)
            assert version is not None
            assert version.workflow_definition == workflow_definition
        if workflow_definition["name"] == failing_name:
            raise error
        return 0

    mock_schedule_sync.reset_mock()
    mock_schedule_sync.side_effect = sync
    token = strict_mode_context_var.set(True)
    try:
        with patch("syntara.workflows.seed_builtin._BUILTIN_DEFINITIONS", definitions):
            with pytest.raises(ScheduledTriggerSyncError) as exc_info:
                async with test_db_session_factory() as session:
                    await seed_builtin_workflows(session)
        assert exc_info.value is error
    finally:
        strict_mode_context_var.reset(token)

    assert mock_schedule_sync.await_count == failure_index + 1
    # Read after the failed seeding session has closed, so its pending writes
    # cannot accidentally make these durability assertions pass.
    async with test_db_session_factory() as reader:
        workflows = (await reader.exec(select(Workflow).where(col(Workflow.is_builtin) == True))).all()  # noqa: E712
        expected_names = {d["name"] for d in definitions} if existing else processed_names
        assert {w.name for w in workflows} == expected_names
        for workflow in workflows:
            processed = workflow.name in processed_names
            expected_version = 2 if existing and processed else 1
            versions = (
                await reader.exec(
                    select(WorkflowVersion)
                    .where(col(WorkflowVersion.workflow_id) == workflow.id)
                    .order_by(col(WorkflowVersion.version))
                )
            ).all()
            assert [v.version for v in versions] == list(range(1, expected_version + 1))
            assert workflow.current_version == expected_version
            assert workflow.published_version_id == versions[-1].id
            expected_definition = next(
                d for d in (definitions if processed else _BUILTIN_DEFINITIONS) if d["name"] == workflow.name
            )
            assert versions[-1].workflow_definition == expected_definition
            events = (
                await reader.exec(
                    select(WorkflowPublishEvent).where(col(WorkflowPublishEvent.workflow_id) == workflow.id)
                )
            ).all()
            assert len(events) == expected_version


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_project", [False, True], ids=["unchanged", "project-correction"])
async def test_identical_rerun_preserves_workflows_versions_and_events(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    mock_schedule_sync: AsyncMock,
    *,
    repair_project: bool,
) -> None:
    """An identical rerun creates no rows and durably repairs a project's assignment."""
    await seed_authz_data(test_db_session)
    workflow_state = select(
        Workflow.id, Workflow.current_version, Workflow.published_version_id, Workflow.project_id
    ).where(col(Workflow.is_builtin) == True)  # noqa: E712
    async with test_db_session_factory() as session:
        await seed_builtin_workflows(session)
        before_workflows = set((await session.exec(workflow_state)).all())
        before_versions = set((await session.exec(select(WorkflowVersion.id))).all())
        before_events = set((await session.exec(select(WorkflowPublishEvent.id))).all())
        assert len(before_workflows) == len(_BUILTIN_DEFINITIONS)
        assert len(before_versions) == len(_BUILTIN_DEFINITIONS)
        assert len(before_events) == len(_BUILTIN_DEFINITIONS)

        if repair_project:
            # Use the final definition so no later definition's commit can
            # accidentally persist its correction if the unchanged commit is missing.
            workflow = (
                await session.exec(select(Workflow).where(col(Workflow.name) == _BUILTIN_DEFINITIONS[-1]["name"]))
            ).one()
            default_project = (await session.exec(select(Project).where(col(Project.name) == "default"))).one()
            assert workflow.project_id != default_project.id
            workflow.project_id = default_project.id
            await session.commit()

    mock_schedule_sync.reset_mock()
    async with test_db_session_factory() as session:
        await seed_builtin_workflows(session)

    # Compare identities and publication state from a fresh session after the
    # rerun session closes, including the corrected built-in project assignment.
    async with test_db_session_factory() as reader:
        assert set((await reader.exec(workflow_state)).all()) == before_workflows
        assert set((await reader.exec(select(WorkflowVersion.id))).all()) == before_versions
        assert set((await reader.exec(select(WorkflowPublishEvent.id))).all()) == before_events
    assert mock_schedule_sync.await_count == len(_BUILTIN_DEFINITIONS)
