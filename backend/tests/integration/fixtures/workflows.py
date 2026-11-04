"""Workflow and execution model fixtures for integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest_asyncio
from sqlmodel import select

from syntara.authz.models.project import Project
from syntara.workflows.models import ActivityExecution, ActivityStatus, Workflow, WorkflowVersion
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest_asyncio.fixture
async def test_workflow_definition() -> dict[str, Any]:
    """Create a test V2 workflow definition."""
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "description": "Test workflow",
        "triggers": [
            {
                "id": "trigger_manual",
                "type": "manual_trigger",
            }
        ],
        "nodes": [
            {
                "id": "test_activity",
                "name": "test_activity",
                "type": "script",
                "parameters": {
                    "language": "bash",
                    "code": "echo 'test'",
                },
            }
        ],
        "edges": [
            {"from": "trigger_manual", "to": "test_activity"},
        ],
    }


@pytest_asyncio.fixture
async def test_workflow(
    test_db_session: AsyncSession, test_user: User, test_workflow_definition: dict[str, Any]
) -> Workflow:
    """Create a test workflow with version."""
    project = Project(name=f"test-project-{uuid4().hex[:8]}", description="Test project")
    test_db_session.add(project)
    await test_db_session.flush()

    workflow = Workflow(
        name="test-workflow",
        description="Test workflow for execution tests",
        created_by=test_user.id,
        is_enabled=False,
        current_version=1,
        project_id=project.id,
    )
    test_db_session.add(workflow)

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=test_workflow_definition,
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.flush()

    workflow.published_version_id = version.id
    workflow.is_enabled = True
    publish_event = WorkflowPublishEvent(
        workflow_id=workflow.id,
        version_id=version.id,
        action=PublishAction.PUBLISHED,
        actor_id=test_user.id,
    )
    test_db_session.add(publish_event)
    await test_db_session.commit()
    return workflow


@pytest_asyncio.fixture
async def form_trigger_workflow_definition() -> dict[str, Any]:
    """Create a workflow definition with Form and Manual Triggers for execution tests."""
    return {
        "schema_version": "2.0.0",
        "name": "form-trigger-test-workflow",
        "description": "Workflow for Form Trigger submission validation tests",
        "triggers": [
            {
                "id": "form",
                "type": "form_trigger",
                "parameters": {
                    "message": "Enter the request details.",
                    "form_definition": {
                        "fields": [
                            {"type": "text", "value_name": "required_text", "label": "Required text", "required": True},
                            {
                                "type": "dropdown",
                                "value_name": "environment",
                                "label": "Environment",
                                "required": False,
                                "options": {
                                    "source": "static",
                                    "values": [{"display_label": "Staging", "value": "staging"}],
                                },
                            },
                            {"type": "number", "value_name": "count", "label": "Count", "required": True},
                            {"type": "date", "value_name": "start", "label": "Start", "required": True},
                            {"type": "email", "value_name": "contact", "label": "Contact", "required": True},
                        ]
                    },
                    "submit_label": "Submit request",
                    "success_message": "Request submitted.",
                    "css_override": "form { color: #333; }",
                },
            },
            {
                "id": "manual",
                "type": "manual_trigger",
                "parameters": {
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "default": "manual-default"},
                            "required_field": {"type": "string"},
                        },
                        "required": ["required_field"],
                    }
                },
            },
        ],
        "nodes": [
            {
                "id": "form_target",
                "name": "Form Target",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo form"},
            },
            {
                "id": "manual_target",
                "name": "Manual Target",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo manual"},
            },
        ],
        "edges": [
            {"from": "form", "to": "form_target"},
            {"from": "manual", "to": "manual_target"},
        ],
    }


@pytest_asyncio.fixture
async def form_trigger_workflow(
    test_db_session: AsyncSession,
    test_user: User,
    form_trigger_workflow_definition: dict[str, Any],
) -> Workflow:
    """Persist a published workflow containing Form and Manual Triggers."""
    project = Project(name=f"form-trigger-project-{uuid4().hex[:8]}", description="Form Trigger test project")
    test_db_session.add(project)
    await test_db_session.flush()

    workflow = Workflow(
        name=f"form-trigger-workflow-{uuid4().hex[:8]}",
        description="Form Trigger submission validation test workflow",
        created_by=test_user.id,
        updated_by=test_user.id,
        is_enabled=False,
        current_version=1,
        project_id=project.id,
    )
    test_db_session.add(workflow)
    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=form_trigger_workflow_definition,
        created_by=test_user.id,
    )
    test_db_session.add(version)
    await test_db_session.flush()

    workflow.published_version_id = version.id
    workflow.is_enabled = True
    test_db_session.add(
        WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=version.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
    )
    await test_db_session.commit()
    await test_db_session.refresh(workflow)
    return workflow


@pytest_asyncio.fixture
async def test_execution(test_db_session: AsyncSession, test_user: User, test_workflow: Workflow) -> Execution:
    """Create a test execution."""
    result = await test_db_session.exec(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == test_workflow.id,
            WorkflowVersion.version == test_workflow.current_version,
        )
    )
    version_id = result.one()

    execution = Execution(
        workflow_id=test_workflow.id,
        workflow_version_id=version_id,
        temporal_workflow_id=f"exec-{uuid4()}",
        status=ExecutionStatus.PENDING,
        input_data={},
        created_by=test_user.id,
        project_id=test_workflow.project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()
    return execution


@pytest_asyncio.fixture
async def test_activity(
    test_db_session: AsyncSession,
    test_execution: Execution,
) -> ActivityExecution:
    """Create a test workflow activity."""
    now = datetime.now(UTC)

    activity = ActivityExecution(
        execution_id=test_execution.id,
        activity_name="test_activity",
        node_type="script",
        temporal_activity_id="temporal-123",
        status=ActivityStatus.COMPLETED,
        labels={"environment": "test"},
        started_at=now,
        completed_at=now,
        input_data={"param": "value"},
        output_data={"result": "success"},
        error_details=None,
        retry_count=0,
        iteration=None,
    )

    test_db_session.add(activity)
    await test_db_session.commit()
    return activity
