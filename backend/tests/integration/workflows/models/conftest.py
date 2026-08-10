"""Shared pytest fixtures for model unit tests."""

from uuid import UUID, uuid4

import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.execution import Execution
from tests.helpers.workflow import create_minimal_workflow_definition


@pytest_asyncio.fixture
async def test_workflow_minimal(
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: UUID,
) -> Workflow:
    """Create a minimal test workflow.

    Args:
        test_db_session: Test database session
        test_user: Test user
        test_project_id: Project ID

    Returns:
        Workflow: Minimal test workflow instance

    """
    workflow = Workflow(
        id=uuid4(),
        name="test-workflow",
        created_by=test_user.id,
        project_id=test_project_id,
    )
    test_db_session.add(workflow)
    await test_db_session.commit()
    return workflow


@pytest_asyncio.fixture
async def test_workflow_version_minimal(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow_minimal: Workflow,
) -> WorkflowVersion:
    """Create a minimal test workflow version.

    Args:
        test_db_session: Test database session
        test_user: Test user
        test_workflow_minimal: Test workflow

    Returns:
        WorkflowVersion: Minimal test workflow version instance

    """
    workflow_version = WorkflowVersion(
        id=uuid4(),
        workflow_id=test_workflow_minimal.id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=create_minimal_workflow_definition(name="test-workflow"),
        created_by=test_user.id,
    )
    test_db_session.add(workflow_version)
    await test_db_session.commit()
    return workflow_version


@pytest_asyncio.fixture
async def test_execution_minimal(
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow_minimal: Workflow,
    test_workflow_version_minimal: WorkflowVersion,
    test_project_id: UUID,
) -> Execution:
    """Create a minimal test execution.

    Args:
        test_db_session: Test database session
        test_user: Test user
        test_workflow_minimal: Test workflow
        test_workflow_version_minimal: Test workflow version
        test_project_id: Project ID

    Returns:
        Execution: Minimal test execution instance

    """
    execution = Execution(
        id=uuid4(),
        workflow_id=test_workflow_minimal.id,
        workflow_version_id=test_workflow_version_minimal.id,
        temporal_workflow_id="test-workflow-123",
        created_by=test_user.id,
        project_id=test_project_id,
    )
    test_db_session.add(execution)
    await test_db_session.commit()
    return execution
