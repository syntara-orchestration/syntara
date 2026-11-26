"""Integration tests for workflow configuration audit summaries."""

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models import User
from syntara.workflows.audit.workflow_version import WorkflowVersionCreatedEvent
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService


def _definition_with_triggers(triggers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a valid script workflow with the provided entry triggers."""
    return {
        "schema_version": "2.0.0",
        "name": "subworkflow-trigger-audit",
        "triggers": triggers,
        "nodes": [
            {
                "id": "build",
                "name": "Build",
                "type": "script",
                "parameters": {"language": "python", "code": "print('build')"},
            }
        ],
        "edges": [{"from": trigger["id"], "to": "build"} for trigger in triggers],
    }


def _manual_trigger() -> dict[str, Any]:
    return {"id": "manual_entry", "type": "manual_trigger", "parameters": {}}


def _subworkflow_trigger(*, input_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "child_entry",
        "type": "subworkflow_trigger",
        "parameters": {
            "input_schema": input_schema,
            "output_schema": {"type": "object", "properties": {"release": {"type": "string"}}},
            "output_mapping": {"release": "${build.stdout}"},
        },
    }


async def _create_published_workflow(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    definition: dict[str, Any],
) -> Workflow:
    workflow = Workflow(
        name=f"workflow-{uuid4().hex[:8]}",
        created_by=created_by,
        project_id=project_id,
        current_version=1,
        is_enabled=False,
    )
    session.add(workflow)
    await session.flush()

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=definition,
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    workflow.published_version_id = version.id
    workflow.is_enabled = True
    await session.commit()
    return workflow


@pytest.mark.integration
@pytest.mark.asyncio
async def test_subworkflow_trigger_changes_are_included_in_version_audits(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manual_trigger = _manual_trigger()
    subworkflow_trigger = _subworkflow_trigger(input_schema={"type": "object", "properties": {}})
    actor_id = test_user.id
    service = WorkflowService(test_db_session, test_user)
    workflow = await _create_published_workflow(
        test_db_session,
        created_by=actor_id,
        project_id=test_project_id,
        definition=_definition_with_triggers([manual_trigger]),
    )
    events: list[object] = []
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", lambda event: events.append(event))

    trigger_changes = [
        (
            _definition_with_triggers([manual_trigger, subworkflow_trigger]),
            "triggers_added",
        ),
        (
            _definition_with_triggers(
                [
                    manual_trigger,
                    _subworkflow_trigger(
                        input_schema={
                            "type": "object",
                            "properties": {"environment": {"type": "string"}},
                        }
                    ),
                ]
            ),
            "triggers_modified",
        ),
        (_definition_with_triggers([manual_trigger]), "triggers_removed"),
    ]

    with (
        patch(
            "syntara.workflows.services.workflow_service.get_system_continue_on_failure",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("syntara.workflows.services.workflow_service.WebhookTriggerService") as webhook_service,
    ):
        webhook_service.return_value.sync_webhook_triggers = AsyncMock()
        expected_version = 1
        for definition, change_key in trigger_changes:
            _, version, _validation_result = await service.update_workflow(
                workflow_id=workflow.id,
                workflow_definition=definition,
                change_description=f"Test {change_key}",
                expected_version=expected_version,
            )
            version_events = [event for event in events if isinstance(event, WorkflowVersionCreatedEvent)]
            assert len(version_events) == 1
            assert version_events[0].user_id == actor_id
            assert version_events[0].change_summary is not None
            assert version_events[0].change_summary[change_key] == [
                {"id": "child_entry", "type": "subworkflow_trigger"}
            ]
            expected_version = version.version
            events.clear()
