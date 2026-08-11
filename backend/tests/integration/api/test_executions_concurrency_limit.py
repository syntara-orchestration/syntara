"""Integration tests for the workflow concurrency limit (POST /api/v1/executions).

Covers the application-level cap introduced in concurrent execution support.:
- Returns HTTP 429 when active executions reach max_concurrent_workflows
- Allows creation when below the limit
- limit=0 (default) disables the check entirely
- Terminal executions are excluded from the active count
- 429 response follows RFC 9457 problem-details format
"""

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow
from syntara.workflows.models.execution import TERMINAL_EXECUTION_STATUSES, Execution, ExecutionStatus
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager


async def _seed_execution(
    session: AsyncSession,
    workflow: Workflow,
    user: User,
    status: ExecutionStatus,
) -> Execution:
    """Insert an Execution row with the given status directly into the DB."""
    result = await session.exec(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == workflow.current_version,
        )
    )
    version_id = result.one()
    execution = Execution(
        workflow_id=workflow.id,
        workflow_version_id=version_id,
        temporal_workflow_id=f"test-concurrency-{uuid4()}",
        status=status,
        input_data={},
        created_by=user.id,
        project_id=workflow.project_id,
    )
    session.add(execution)
    await session.commit()
    return execution


_EXECUTE_PAYLOAD = {"trigger_node_id": "trigger_manual"}


@pytest.mark.asyncio
async def test_concurrency_limit_blocks_at_limit(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    override_settings: "Callable[..., AbstractContextManager[object]]",
) -> None:
    """Returns 429 when active execution count equals max_concurrent_workflows."""
    await _seed_execution(test_db_session, test_workflow, test_user, ExecutionStatus.RUNNING)
    await _seed_execution(test_db_session, test_workflow, test_user, ExecutionStatus.PENDING)

    with override_settings(max_concurrent_workflows=2):
        response = await auth_client.post(
            "/api/v1/executions",
            json={"workflow_id": str(test_workflow.id), **_EXECUTE_PAYLOAD},
        )

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "WORKFLOW_CONCURRENCY_LIMIT"
    assert body["retryable"] is True


@pytest.mark.asyncio
async def test_concurrency_limit_allows_below_limit(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    override_settings: "Callable[..., AbstractContextManager[object]]",
) -> None:
    """Allows execution creation when active count is strictly below the limit."""
    await _seed_execution(test_db_session, test_workflow, test_user, ExecutionStatus.RUNNING)

    with override_settings(max_concurrent_workflows=2):
        response = await auth_client.post(
            "/api/v1/executions",
            json={"workflow_id": str(test_workflow.id), **_EXECUTE_PAYLOAD},
        )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_concurrency_limit_zero_disables_check(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    override_settings: "Callable[..., AbstractContextManager[object]]",
) -> None:
    """limit=0 (the default) disables the concurrency check entirely."""
    for _ in range(5):
        await _seed_execution(test_db_session, test_workflow, test_user, ExecutionStatus.RUNNING)

    with override_settings(max_concurrent_workflows=0):
        response = await auth_client.post(
            "/api/v1/executions",
            json={"workflow_id": str(test_workflow.id), **_EXECUTE_PAYLOAD},
        )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_concurrency_limit_excludes_terminal_executions(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    override_settings: "Callable[..., AbstractContextManager[object]]",
) -> None:
    """Completed, failed, and cancelled executions are not counted against the limit."""
    for status in TERMINAL_EXECUTION_STATUSES:
        await _seed_execution(test_db_session, test_workflow, test_user, status)

    with override_settings(max_concurrent_workflows=1):
        response = await auth_client.post(
            "/api/v1/executions",
            json={"workflow_id": str(test_workflow.id), **_EXECUTE_PAYLOAD},
        )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_concurrency_limit_rfc9457_response_shape(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    test_workflow: Workflow,
    override_settings: "Callable[..., AbstractContextManager[object]]",
) -> None:
    """429 body follows RFC 9457 problem-details with correct field values."""
    await _seed_execution(test_db_session, test_workflow, test_user, ExecutionStatus.RUNNING)

    with override_settings(max_concurrent_workflows=1):
        response = await auth_client.post(
            "/api/v1/executions",
            json={"workflow_id": str(test_workflow.id), **_EXECUTE_PAYLOAD},
        )

    assert response.status_code == 429
    body = response.json()
    assert "rate-limited" in body["type"]
    assert body["title"] == "Workflow Concurrency Limit Reached"
    assert "1/1" in body["detail"]
    assert body["retryable"] is True
    assert body["code"] == "WORKFLOW_CONCURRENCY_LIMIT"
