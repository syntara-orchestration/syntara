"""Integration tests for POST /api/v1/executions/{id}/validate-restart and /restart (AAP-92820)."""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionMode, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.responses import WorkflowStartResponse
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.integration.helpers.error_data import assert_error_data

GRAPH_NODES = [
    {"id": "trigger_manual", "name": "Manual trigger", "type": "manual_trigger", "parameters": {}},
    {"id": "step_1", "name": "step-1", "type": "script", "parameters": {"code": "echo hi"}},
    {"id": "step_2", "name": "step-2", "type": "script", "parameters": {"code": "exit 1"}},
    {"id": "step_3", "name": "step-3", "type": "script", "parameters": {"code": "echo done"}},
]
GRAPH_EDGES = [
    {"from": "trigger_manual", "to": "step_1"},
    {"from": "step_1", "to": "step_2"},
    {"from": "step_2", "to": "step_3"},
]


@pytest.fixture
def mock_temporal_service(session_app) -> Generator[Mock, None, None]:
    """Override temporal service dependency with a mock."""
    from syntara.workflows.executions_router import get_temporal_execution_service

    mock_service = Mock(spec=TemporalExecutionService)

    new_execution_id = str(uuid.uuid4())
    mock_service.start_workflow = AsyncMock(
        return_value=WorkflowStartResponse(
            execution_id=new_execution_id,
            workflow_id="wf-mock",
            temporal_workflow_id=f"temporal-{new_execution_id}",
            temporal_run_id=f"run-{new_execution_id}",
            status="RUNNING",
            started_at="2026-01-01T00:00:00Z",
        )
    )

    async def override_get_temporal_service() -> Mock:
        return mock_service

    session_app.dependency_overrides[get_temporal_execution_service] = override_get_temporal_service

    yield mock_service

    session_app.dependency_overrides.pop(get_temporal_execution_service, None)


async def _set_version_definition(session: AsyncSession, workflow: Workflow, nodes: list[dict]) -> WorkflowVersion:
    """Point the workflow's current version at a small graph definition."""
    result = await session.exec(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == workflow.current_version,
        )
    )
    version = result.one()
    version.workflow_definition = {
        "schema_version": "2.0.0",
        "name": workflow.name,
        "triggers": [{"id": "trigger_manual", "name": "Manual trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": GRAPH_EDGES,
    }
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def _create_execution(
    session: AsyncSession,
    workflow: Workflow,
    user: User,
    *,
    execution_status: ExecutionStatus = ExecutionStatus.FAILED,
) -> Execution:
    """Create a test execution record."""
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
        temporal_workflow_id=f"temporal-{uuid.uuid4()}",
        status=execution_status,
        created_by=user.id,
        input_data={"key": "value"},
        labels={},
        project_id=workflow.project_id,
        mode=ExecutionMode.STANDARD,
        trigger_node_id="trigger_manual",
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    return execution


async def _add_failed_activity(session: AsyncSession, execution: Execution, node_id: str = "step_2") -> None:
    """Record a failed activity for a node."""
    session.add(
        ActivityExecution(
            execution_id=execution.id,
            activity_name=node_id,
            node_type=NodeType.SCRIPT,
            temporal_activity_id=f"temporal-activity-{uuid.uuid4()}",
            status=ActivityStatus.FAILED,
            error_details="boom",
        )
    )
    await session.commit()


async def _add_completed_activity(
    session: AsyncSession, execution: Execution, node_id: str, output: dict | None = None
) -> None:
    """Record a completed activity with stored output for a node."""
    session.add(
        ActivityExecution(
            execution_id=execution.id,
            activity_name=node_id,
            node_type=NodeType.SCRIPT,
            temporal_activity_id=f"temporal-activity-{uuid.uuid4()}",
            status=ActivityStatus.COMPLETED,
            output_data=output if output is not None else {"result": "ok"},
        )
    )
    await session.commit()


async def _save_new_version(
    session: AsyncSession, workflow: Workflow, user: User, nodes: list[dict], edges: list[dict] | None = None
) -> None:
    """Save a new current version with the given nodes (snapshot stays behind)."""
    test_db_user_id = user.id
    session.add(
        WorkflowVersion(
            workflow_id=workflow.id,
            version=workflow.current_version + 1,
            schema_version="2.0.0",
            workflow_definition={
                "schema_version": "2.0.0",
                "name": workflow.name,
                "triggers": [
                    {"id": "trigger_manual", "name": "Manual trigger", "type": "manual_trigger", "parameters": {}}
                ],
                "nodes": nodes,
                "edges": edges if edges is not None else GRAPH_EDGES,
            },
            created_by=test_db_user_id,
            updated_by=test_db_user_id,
        )
    )
    workflow.current_version += 1
    session.add(workflow)
    await session.commit()


async def _eligible_execution(session: AsyncSession, workflow: Workflow, user: User) -> Execution:
    """Execution eligible for restart: FAILED + failed step_2 + matching definition."""
    await _set_version_definition(session, workflow, GRAPH_NODES)
    execution = await _create_execution(session, workflow, user)
    await _add_failed_activity(session, execution)
    return execution


@pytest.mark.asyncio
class TestValidateRestart:
    """Integration tests for POST /executions/{execution_id}/validate-restart."""

    async def test_validate_pass(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/validate-restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is True
        assert data["reason"] is None
        assert data["failure_point_ids"] == ["step_2"]

    async def test_validate_rejects_non_restartable_state(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        execution.status = ExecutionStatus.COMPLETED
        test_db_session.add(execution)
        await test_db_session.commit()

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/validate-restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is False
        assert "completed" in data["reason"]

    async def test_validate_rejects_unknown_failure_point(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/validate-restart",
            json={"failure_point_ids": ["step_3"]},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["eligible"] is False

    async def test_validate_rejects_upstream_change(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        # Save a NEW version with an upstream change; the execution snapshot stays on the old one.
        changed = [
            dict(node, parameters={"code": "exit 0"}) if node["id"] == "step_1" else node for node in GRAPH_NODES
        ]
        await _save_new_version(test_db_session, test_workflow, test_user, changed)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/validate-restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is False
        assert data["changed_node_ids"] == ["step_1"]

    async def test_validate_rejects_inserted_upstream_node(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        gate = {"id": "step_1b", "name": "gate", "type": "script", "parameters": {"code": "echo gate"}}
        gate_edges = [
            {"from": "trigger_manual", "to": "step_1"},
            {"from": "step_1", "to": "step_1b"},
            {"from": "step_1b", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
        ]
        await _save_new_version(
            test_db_session, test_workflow, test_user, [GRAPH_NODES[0], gate, *GRAPH_NODES[1:]], gate_edges
        )

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/validate-restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is False
        assert data["changed_node_ids"] == ["step_1b"]

    async def test_validate_rejects_sanitized_upstream_output(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        await _add_completed_activity(test_db_session, execution, "step_1", {"token": "[REDACTED]"})

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/validate-restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is False
        assert data["sanitized_node_ids"] == ["step_1"]

    async def test_validate_missing_execution_returns_404(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            f"/api/v1/executions/{uuid.uuid4()}/validate-restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Execution Not Found",
            detail="The requested execution was not found",
            code="EXECUTION_NOT_FOUND",
            retryable=False,
        )


@pytest.mark.asyncio
class TestRestartExecution:
    """Integration tests for POST /executions/{execution_id}/restart."""

    async def test_restart_success(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "pending"
        assert data["source_execution_id"] == str(execution.id)
        assert data["failed_node_ids"] == ["step_2"]
        assert data["triggered_by"] == str(test_user.id)
        assert data["restart_count"] == 1
        version_result = await test_db_session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        assert data["workflow_version_id"] == str(version_result.one())

        mock_temporal_service.start_workflow.assert_called_once()
        _, kwargs = mock_temporal_service.start_workflow.call_args
        assert kwargs["workflow_metadata"]["restart"]["restart_from_execution_id"] == str(execution.id)
        assert kwargs["workflow_metadata"]["restart"]["failure_point_ids"] == ["step_2"]

    async def test_restart_rejected_state_returns_409(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        execution.status = ExecutionStatus.RUNNING
        test_db_session.add(execution)
        await test_db_session.commit()

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Execution Not Restartable",
            detail=data["detail"],
            code="EXECUTION_NOT_RESTARTABLE",
            retryable=False,
        )

    async def test_restart_missing_execution_returns_404(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            f"/api/v1/executions/{uuid.uuid4()}/restart",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
