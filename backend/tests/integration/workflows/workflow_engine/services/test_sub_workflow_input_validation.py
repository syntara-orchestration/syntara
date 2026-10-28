"""Child input-schema validation for sub-workflow invocation (AAP-91265).

The setup activity validates the invocation input against the child
``subworkflow_trigger``'s declared ``input_schema`` before creating the child
execution. These tests exercise that validation against the real,
alembic-built PostgreSQL schema by calling ``SubWorkflowSetupActivity.run``
directly (it uses no Temporal activity context).

Story: AAP-91265 (input validation portion).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import (
    SubWorkflowSetupActivity,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-input-validation"


def _child_def(input_schema: dict[str, Any] | None) -> dict[str, Any]:
    """Child definition whose subworkflow_trigger optionally declares an input schema."""
    trigger_params: dict[str, Any] = {"input_schema": input_schema} if input_schema is not None else {}
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "child_trigger", "type": "subworkflow_trigger", "parameters": trigger_params}],
        "nodes": [{"id": "child_script", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}}],
        "edges": [{"from": "child_trigger", "to": "child_script"}],
    }


async def _create_published_child(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    input_schema: dict[str, Any] | None,
) -> UUID:
    """Create and publish a child workflow with the given trigger input schema."""
    workflow_id = uuid4()
    workflow = Workflow(
        id=workflow_id,
        name=f"child-{workflow_id.hex[:8]}",
        created_by=created_by,
        project_id=project_id,
    )
    session.add(workflow)
    await session.flush()
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=_child_def(input_schema),
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    workflow.is_enabled = True
    workflow.published_version_id = version.id
    await session.commit()
    return workflow_id


def _params(workflow_id: UUID, input_mapping: dict[str, Any]) -> dict[str, Any]:
    return {"workflow_id": str(workflow_id), "trigger_node_id": "child_trigger", "input_mapping": input_mapping}


_REQUIRE_GREETING: dict[str, Any] = {
    "type": "object",
    "properties": {"greeting": {"type": "string"}},
    "required": ["greeting"],
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_valid_input_passes(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """Input conforming to the declared schema is accepted."""
    wf_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=test_project_id, input_schema=_REQUIRE_GREETING
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(_params(wf_id, {"greeting": "hi"}), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    assert result["child_workflow_version"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_required_field_raises_non_retryable_naming_field(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A missing required input raises a non-retryable error naming the field."""
    wf_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=test_project_id, input_schema=_REQUIRE_GREETING
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    with pytest.raises(ApplicationError) as exc_info:
        await setup.run(_params(wf_id, {}), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    assert exc_info.value.type == "SubWorkflowInputValidationError"
    assert exc_info.value.non_retryable is True
    assert "greeting" in str(exc_info.value)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wrong_type_raises_non_retryable(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """An input of the wrong type raises a non-retryable validation error."""
    wf_id = await _create_published_child(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        input_schema={"type": "object", "properties": {"greeting": {"type": "string"}}},
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    with pytest.raises(ApplicationError) as exc_info:
        await setup.run(_params(wf_id, {"greeting": 123}), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    assert exc_info.value.type == "SubWorkflowInputValidationError"
    assert exc_info.value.non_retryable is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_input_schema_skips_validation(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """When the trigger declares no input_schema, any input is accepted."""
    wf_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=test_project_id, input_schema=None
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(_params(wf_id, {"anything": 1}), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    assert result["child_workflow_version"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_default_is_applied_to_child_input(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A schema default is filled into the input passed to the child."""
    wf_id = await _create_published_child(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        input_schema={
            "type": "object",
            "properties": {"greeting": {"type": "string", "default": "hello"}},
        },
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(_params(wf_id, {}), str(uuid4()), "sub_wf_node", str(test_user.id), 0)

    async with test_db_session_factory() as session:
        child_execution = await session.get(Execution, UUID(result["execution_id"]))
    assert child_execution is not None
    assert child_execution.input_data == {"greeting": "hello"}
