"""Integration tests for AAP-87750.

Deleting a workflow that has a paused execution with a pending approval must
cancel the run and its approval rather than leaving both orphaned.

The bug: DELETE returned 204, the approval stayed 'pending' and was still
decidable (PATCH returned 200 with no effect), and the execution stayed 'paused'
forever because nothing ever told Temporal to stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from syntara.approvals.models.api_models import ApprovalRequestStatus
from syntara.approvals.models.approval_request import ApprovalRequest
from syntara.workflows.models import Workflow
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from collections.abc import Generator

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
def mock_temporal_service(session_app) -> Generator[Mock, None, None]:
    """Override the Temporal dependency so the delete route can cancel runs."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    mock_service = Mock(spec=TemporalExecutionService)
    mock_service.cancel_workflow = AsyncMock()

    async def override() -> Mock:
        return mock_service

    session_app.dependency_overrides[get_temporal_execution_service] = override
    yield mock_service
    session_app.dependency_overrides.pop(get_temporal_execution_service, None)


async def _paused_run_awaiting_approval(
    session: AsyncSession,
    project_id,
    user_id,
    *,
    launcher_id: str | None = None,
) -> tuple[UUID, UUID, str]:
    """Build a published workflow with a paused execution and a pending approval.

    Returns plain (workflow_id, approval_id, temporal_workflow_id) rather than ORM
    objects, so nothing lazy-loads after the commit.
    """
    workflow_id, version_id, execution_id = uuid4(), uuid4(), uuid4()
    approval_id = uuid4()
    temporal_workflow_id = f"test-temporal-{uuid4().hex[:8]}"

    workflow = Workflow(
        id=workflow_id,
        name=f"approval-delete-{uuid4().hex[:8]}",
        project_id=project_id,
        created_by=user_id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="approval-delete"),
    )
    session.add(workflow)
    await session.flush()

    version = WorkflowVersion(
        id=version_id,
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        created_by=user_id,
        workflow_definition=create_minimal_workflow_definition(name="approval-delete"),
    )
    session.add(version)
    await session.flush()

    execution = Execution(
        id=execution_id,
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        project_id=project_id,
        created_by=user_id,
        status=ExecutionStatus.PAUSED,
        temporal_workflow_id=temporal_workflow_id,
        launcher_temporal_workflow_id=launcher_id,
    )
    session.add(execution)

    approval = ApprovalRequest(
        id=approval_id,
        project_id=project_id,
        name="Review Gate",
        execution_id=execution_id,
        approval_node_id="approval_gate",
        status=ApprovalRequestStatus.PENDING,
        created_by=user_id,
    )
    session.add(approval)
    await session.commit()

    return workflow_id, approval_id, temporal_workflow_id


@pytest.mark.asyncio
async def test_delete_cancels_run_and_approval(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    mock_temporal_service: Mock,
) -> None:
    """The ticket's repro: delete must not leave the approval pending."""
    workflow_id, approval_id, temporal_workflow_id = await _paused_run_awaiting_approval(
        test_db_session, test_project_id, test_user.id
    )

    response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 204

    mock_temporal_service.cancel_workflow.assert_awaited_once_with(temporal_workflow_id=temporal_workflow_id)

    test_db_session.expire_all()
    result = await test_db_session.exec(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
    db_approval = result.one()

    assert db_approval.status == ApprovalRequestStatus.CANCELLED, "Approval left pending — this is the AAP-87750 orphan"
    assert db_approval.decision_notes == "Workflow was deleted"
    assert db_approval.decided_at is not None


@pytest.mark.asyncio
async def test_cancelled_approval_can_no_longer_be_decided(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    mock_temporal_service: Mock,
) -> None:
    """Step 6 of the repro: PATCH used to return 200 with no effect; now 409."""
    workflow_id, approval_id, _temporal_id = await _paused_run_awaiting_approval(
        test_db_session, test_project_id, test_user.id
    )

    assert (await auth_client.delete(f"/api/v1/workflows/{workflow_id}")).status_code == 204

    response = await auth_client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
    )
    assert response.status_code == 409, f"Expected conflict, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_scheduled_execution_cancels_parent_launcher(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    mock_temporal_service: Mock,
) -> None:
    """Scheduled runs must cancel the launcher, not the child that may not exist yet."""
    workflow_id, _approval_id, _temporal_id = await _paused_run_awaiting_approval(
        test_db_session, test_project_id, test_user.id, launcher_id="scheduled-launcher-42"
    )

    assert (await auth_client.delete(f"/api/v1/workflows/{workflow_id}")).status_code == 204

    mock_temporal_service.cancel_workflow.assert_awaited_once_with(temporal_workflow_id="scheduled-launcher-42")


@pytest.mark.asyncio
async def test_terminal_execution_is_not_cancelled(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    mock_temporal_service: Mock,
) -> None:
    """Deleting a workflow whose runs already finished must not call Temporal."""
    workflow_id, version_id = uuid4(), uuid4()
    workflow = Workflow(
        id=workflow_id,
        name=f"finished-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="finished"),
    )
    test_db_session.add(workflow)
    await test_db_session.flush()
    test_db_session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            created_by=test_user.id,
            workflow_definition=create_minimal_workflow_definition(name="finished"),
        )
    )
    await test_db_session.flush()
    test_db_session.add(
        Execution(
            id=uuid4(),
            workflow_id=workflow_id,
            workflow_version_id=version_id,
            project_id=test_project_id,
            created_by=test_user.id,
            status=ExecutionStatus.COMPLETED,
            temporal_workflow_id=f"test-temporal-{uuid4().hex[:8]}",
        )
    )
    await test_db_session.commit()

    assert (await auth_client.delete(f"/api/v1/workflows/{workflow_id}")).status_code == 204

    mock_temporal_service.cancel_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_temporal_has_no_record_of_is_finalised(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    mock_temporal_service: Mock,
) -> None:
    """A stale row must not be left non-terminal — that is the ticket's symptom.

    Execution status sync is asynchronous and does not run when the worker is down,
    so rows go stale routinely. Temporal answering NOT_FOUND means no cancellation
    event will ever arrive, so the delete has to finalise the row itself.
    """
    workflow_id, _approval_id, _temporal_id = await _paused_run_awaiting_approval(
        test_db_session, test_project_id, test_user.id
    )
    execution_result = await test_db_session.exec(select(Execution).where(Execution.workflow_id == workflow_id))
    execution_id = execution_result.one().id

    # False = Temporal has no such run.
    mock_temporal_service.cancel_workflow = AsyncMock(return_value=False)

    assert (await auth_client.delete(f"/api/v1/workflows/{workflow_id}")).status_code == 204

    test_db_session.expire_all()
    result = await test_db_session.exec(select(Execution).where(Execution.id == execution_id))
    execution = result.one()

    assert execution.status == ExecutionStatus.CANCELLED, (
        f"Stale execution left non-terminal ({execution.status}) — AAP-87750 symptom recreated"
    )
    assert execution.completed_at is not None
    assert execution.completed_at > execution.created_at


@pytest.mark.asyncio
async def test_pending_approval_on_terminal_execution_is_cancelled(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    mock_temporal_service: Mock,
) -> None:
    """A failed run can still hold a pending approval.

    The engine only cleans approvals up on CancelledError, so nothing cancels this
    one — and once workflow_id is NULLed it can never be found again.
    """
    workflow_id, version_id, execution_id = uuid4(), uuid4(), uuid4()
    approval_id = uuid4()

    workflow = Workflow(
        id=workflow_id,
        name=f"failed-with-approval-{uuid4().hex[:8]}",
        project_id=test_project_id,
        created_by=test_user.id,
        current_version=1,
        is_enabled=False,
        workflow_definition=create_minimal_workflow_definition(name="failed-with-approval"),
    )
    test_db_session.add(workflow)
    await test_db_session.flush()
    test_db_session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            created_by=test_user.id,
            workflow_definition=create_minimal_workflow_definition(name="failed-with-approval"),
        )
    )
    await test_db_session.flush()
    test_db_session.add(
        Execution(
            id=execution_id,
            workflow_id=workflow_id,
            workflow_version_id=version_id,
            project_id=test_project_id,
            created_by=test_user.id,
            status=ExecutionStatus.FAILED,
            temporal_workflow_id=f"test-temporal-{uuid4().hex[:8]}",
        )
    )
    test_db_session.add(
        ApprovalRequest(
            id=approval_id,
            project_id=test_project_id,
            name="Stranded Gate",
            execution_id=execution_id,
            approval_node_id="approval_gate",
            status=ApprovalRequestStatus.PENDING,
            created_by=test_user.id,
        )
    )
    await test_db_session.commit()

    assert (await auth_client.delete(f"/api/v1/workflows/{workflow_id}")).status_code == 204

    # The run was already terminal, so Temporal must not be asked to cancel it.
    mock_temporal_service.cancel_workflow.assert_not_awaited()

    test_db_session.expire_all()
    result = await test_db_session.exec(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
    assert result.one().status == ApprovalRequestStatus.CANCELLED, (
        "Approval on a terminal execution left pending — unreachable once workflow_id is NULL"
    )


@pytest.mark.asyncio
async def test_delete_returns_503_when_temporal_is_unavailable(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    session_app,
) -> None:
    """Fail closed: runs in flight and no Temporal client means the delete is refused."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    workflow_id, _approval_id, _temporal_id = await _paused_run_awaiting_approval(
        test_db_session, test_project_id, test_user.id
    )

    async def no_temporal() -> None:
        return None

    session_app.dependency_overrides[get_temporal_execution_service] = no_temporal
    try:
        response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    finally:
        session_app.dependency_overrides.pop(get_temporal_execution_service, None)

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "TEMPORAL_UNAVAILABLE", f"contract mismatch: {body}"
    assert body["retryable"] is True

    # The workflow must still be there.
    test_db_session.expire_all()
    result = await test_db_session.exec(select(Workflow).where(Workflow.id == workflow_id))
    assert result.one_or_none() is not None


@pytest.mark.asyncio
async def test_delete_without_temporal_succeeds_when_nothing_is_running(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_project_id,
    test_user,
    session_app,
) -> None:
    """A Temporal outage must not make never-run workflows undeletable."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    workflow_id = uuid4()
    test_db_session.add(
        Workflow(
            id=workflow_id,
            name=f"never-run-{uuid4().hex[:8]}",
            project_id=test_project_id,
            created_by=test_user.id,
            current_version=1,
            is_enabled=False,
            workflow_definition=create_minimal_workflow_definition(name="never-run"),
        )
    )
    await test_db_session.commit()

    async def no_temporal() -> None:
        return None

    session_app.dependency_overrides[get_temporal_execution_service] = no_temporal
    try:
        response = await auth_client.delete(f"/api/v1/workflows/{workflow_id}")
    finally:
        session_app.dependency_overrides.pop(get_temporal_execution_service, None)

    assert response.status_code == 204
