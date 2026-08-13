"""Integration tests for the schedule reconciliation worker.

Exercises the reconciliation DB query against a real PostgreSQL instance
to catch type-cast issues (e.g. jsonb_path_exists requiring ::jsonpath)
that unit tests with mocked sessions cannot detect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.models.project import Project
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workers.schedule_reconciliation import reconcile_scheduled_triggers

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_PATCH_SVC = "syntara.workflows.workers.schedule_reconciliation.ScheduledTriggerService"


def _workflow_definition_with_scheduled_trigger(trigger_id: str = "t_sched") -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "scheduled-test",
        "description": "Workflow with a scheduled trigger",
        "triggers": [
            {
                "id": trigger_id,
                "type": "scheduled_trigger",
                "parameters": {
                    "schedule_type": "interval",
                    "interval": "R/2026-01-01T00:00:00Z/PT1H",
                },
            },
        ],
        "nodes": [
            {
                "id": "noop",
                "name": "noop",
                "type": "script",
                "parameters": {"language": "bash", "code": "true"},
            },
        ],
        "edges": [{"from": trigger_id, "to": "noop"}],
    }


async def _seed_published_workflow(
    session: AsyncSession,
    user: User,
    definition: dict[str, Any],
) -> Workflow:
    project = Project(name=f"recon-test-{uuid4().hex[:8]}", description="reconciliation test")
    session.add(project)
    await session.flush()

    workflow = Workflow(
        name="recon-test-workflow",
        description="For schedule reconciliation integration test",
        created_by=user.id,
        is_enabled=False,
        current_version=1,
        project_id=project.id,
    )
    session.add(workflow)
    await session.flush()

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=definition,
        created_by=user.id,
    )
    session.add(version)
    await session.flush()

    workflow.published_version_id = version.id
    workflow.is_enabled = True
    session.add(
        WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=user.id,
        )
    )
    await session.commit()
    return workflow


@pytest.mark.asyncio
async def test_reconciliation_query_with_scheduled_trigger(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
) -> None:
    """The jsonb_path_exists filter should execute without type errors on real PostgreSQL."""
    workflow = await _seed_published_workflow(
        test_db_session,
        test_user,
        _workflow_definition_with_scheduled_trigger(),
    )

    with patch(_PATCH_SVC) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.get_client = AsyncMock(return_value=MagicMock())
        mock_svc.list_all_schedules = AsyncMock(return_value=set())
        mock_svc.create_schedule = AsyncMock(return_value="ok")
        mock_svc_cls.delete_schedule = AsyncMock()

        await reconcile_scheduled_triggers(test_db_session_factory)

        assert mock_svc.create_schedule.call_count == 1
        args = mock_svc.create_schedule.call_args[0]
        assert args[0] == str(workflow.id)
        assert args[1] == "t_sched"


@pytest.mark.asyncio
async def test_reconciliation_query_excludes_manual_only_workflows(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
) -> None:
    """Workflows with only manual triggers should not appear in reconciliation results."""
    manual_only_def = {
        "schema_version": "2.0.0",
        "name": "manual-only",
        "description": "No scheduled triggers",
        "triggers": [{"id": "t_manual", "type": "manual_trigger"}],
        "nodes": [
            {
                "id": "noop",
                "name": "noop",
                "type": "script",
                "parameters": {"language": "bash", "code": "true"},
            },
        ],
        "edges": [{"from": "t_manual", "to": "noop"}],
    }
    await _seed_published_workflow(test_db_session, test_user, manual_only_def)

    with patch(_PATCH_SVC) as mock_svc_cls:
        mock_svc = mock_svc_cls.return_value
        mock_svc.get_client = AsyncMock(return_value=MagicMock())
        mock_svc.list_all_schedules = AsyncMock(return_value=set())
        mock_svc.create_schedule = AsyncMock()
        mock_svc_cls.delete_schedule = AsyncMock()

        await reconcile_scheduled_triggers(test_db_session_factory)

        mock_svc.create_schedule.assert_not_called()
