"""Integration tests for retry-from-failure endpoints (AAP-92820)."""

import uuid
from collections.abc import Generator
from typing import Any
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
from tests.helpers.user_reference import assert_user_reference
from tests.integration.helpers.error_data import assert_error_data

GRAPH_NODES: list[dict[str, Any]] = [
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


async def _set_version_definition(
    session: AsyncSession,
    workflow: Workflow,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowVersion:
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
        "edges": edges if edges is not None else GRAPH_EDGES,
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
    session: AsyncSession,
    execution: Execution,
    node_id: str,
    output: dict[str, Any] | None = None,
    node_type: NodeType = NodeType.SCRIPT,
) -> None:
    """Record a completed activity with stored output for a node."""
    session.add(
        ActivityExecution(
            execution_id=execution.id,
            activity_name=node_id,
            node_type=node_type,
            temporal_activity_id=f"temporal-activity-{uuid.uuid4()}",
            status=ActivityStatus.COMPLETED,
            output_data=output if output is not None else {"result": "ok"},
        )
    )
    await session.commit()


CONVERGE_NODES = [
    {"id": "step_a", "name": "branch-a", "type": "script", "parameters": {"code": "exit 1"}},
    {"id": "step_b", "name": "branch-b", "type": "script", "parameters": {"code": "echo ok"}},
    {"id": "conv_1", "name": "join", "type": "converge", "parameters": {}},
    {"id": "step_3", "name": "after", "type": "script", "parameters": {"code": "echo done"}},
]
CONVERGE_EDGES = [
    {"from": "trigger_manual", "to": "step_a"},
    {"from": "trigger_manual", "to": "step_b"},
    {"from": "step_a", "to": "conv_1"},
    {"from": "step_b", "to": "conv_1"},
    {"from": "conv_1", "to": "step_3"},
]


async def _converge_execution(
    session: AsyncSession, workflow: Workflow, user: User, converge_status: ActivityStatus
) -> Execution:
    """Execution with a failed branch; converge completed or failed."""
    await _set_version_definition(session, workflow, CONVERGE_NODES, CONVERGE_EDGES)
    execution = await _create_execution(session, workflow, user)
    await _add_failed_activity(session, execution, "step_a")
    await _add_completed_activity(session, execution, "step_b")
    session.add(
        ActivityExecution(
            execution_id=execution.id,
            activity_name="conv_1",
            node_type=NodeType.CONVERGE,
            temporal_activity_id=f"temporal-activity-{uuid.uuid4()}",
            status=converge_status,
        )
    )
    await session.commit()
    return execution


async def _save_new_version(
    session: AsyncSession,
    workflow: Workflow,
    user: User,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
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
    """Execution eligible for retry: FAILED + failed step_2 + matching definition."""
    await _set_version_definition(session, workflow, GRAPH_NODES)
    execution = await _create_execution(session, workflow, user)
    await _add_failed_activity(session, execution)
    return execution


@pytest.mark.asyncio
class TestPreviewRetryFromFailure:
    """Integration tests for GET /executions/{execution_id}/retry-from-failure-preview.

    The preview takes no failure-point selection, so every case here exercises the default
    (all currently failed nodes). Fixtures below each have a single failed node, which makes the
    default equivalent to an explicit one-shot selection. Explicit-selection behaviour is covered
    in TestRetryExecution, which is the only endpoint that accepts one.
    """

    async def test_preview_pass(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is True
        assert data["reason"] is None
        assert data["failure_point_ids"] == ["step_2"]
        assert data["step_count_by_eligible_point"] == {"step_2": 2}
        assert data["total_step_count"] == 2

    async def test_preview_empty_selection_defaults_to_all_failed(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """SDP R11/AC-15: an empty selection is the default (all currently failed nodes), not an error."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is True
        assert data["failure_point_ids"] == ["step_2"]
        assert data["auto_included_node_ids"] == []
        assert data["sanitized_replacements"] == {}

    async def test_preview_rejects_non_retryable_state(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        execution.status = ExecutionStatus.COMPLETED
        test_db_session.add(execution)
        await test_db_session.commit()

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is False
        assert "completed" in data["reason"]

    async def test_preview_ignores_later_definition_changes(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """SDP R10: retry is pinned to the retained version; later saves never affect it."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        # Save a NEW version with an upstream change and an inserted node; the execution
        # snapshot stays on the old one, so this must have zero effect on eligibility.
        gate = {"id": "step_1b", "name": "gate", "type": "script", "parameters": {"code": "echo gate"}}
        gate_edges = [
            {"from": "trigger_manual", "to": "step_1"},
            {"from": "step_1", "to": "step_1b"},
            {"from": "step_1b", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
        ]
        changed = [
            dict(node, parameters={"code": "exit 0"}) if node["id"] == "step_1" else node for node in GRAPH_NODES
        ]
        await _save_new_version(test_db_session, test_workflow, test_user, [changed[0], gate, *changed[1:]], gate_edges)

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is True

    async def test_preview_default_selection_auto_includes_sanitized_dependency(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """SDP AC-15/R9a Q4: with the default selection, a sanitized dependency is auto-included, not rejected."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        await _add_completed_activity(test_db_session, execution, "step_1", {"token": "[REDACTED]", "stderr": ""})
        result = await test_db_session.exec(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        version = result.one()
        definition = dict(version.workflow_definition)
        definition["nodes"] = [
            dict(node, parameters={**node.get("parameters", {}), "input_ref": "${step_1.token}"})
            if node.get("id") == "step_2"
            else node
            for node in definition.get("nodes", [])
        ]
        version.workflow_definition = definition
        test_db_session.add(version)
        await test_db_session.commit()

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is True
        assert data["failure_point_ids"] == ["step_1"]
        assert data["auto_included_node_ids"] == ["step_1"]
        assert data["step_count_by_eligible_point"] == {"step_1": 3}
        assert data["sanitized_node_ids"] == []
        assert data["sanitized_replacements"] == {"step_2": ["step_1"]}

    async def test_preview_rejects_failure_under_completed_converge(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _converge_execution(test_db_session, test_workflow, test_user, ActivityStatus.COMPLETED)

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is False
        assert "conv_1" in data["reason"]

    async def test_preview_allows_failure_under_failed_converge(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _converge_execution(test_db_session, test_workflow, test_user, ActivityStatus.FAILED)

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["eligible"] is True

    async def test_preview_allows_clean_field_despite_marker_elsewhere(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        nodes = [
            dict(node, parameters={**node.get("parameters", {}), "input_ref": "${step_1.status_code}"})
            if node.get("id") == "step_2"
            else node
            for node in GRAPH_NODES
        ]
        await _set_version_definition(test_db_session, test_workflow, nodes)
        execution = await _create_execution(test_db_session, test_workflow, test_user)
        await _add_failed_activity(test_db_session, execution, "step_2")
        await _add_completed_activity(
            test_db_session, execution, "step_1", {"status_code": 200, "password": "[REDACTED]", "stderr": ""}
        )

        response = await auth_client.get(f"/api/v1/executions/{execution.id}/retry-from-failure-preview")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["eligible"] is True
        assert data["sanitized_node_ids"] == []

    async def test_preview_missing_execution_returns_404(self, auth_client: AsyncClient) -> None:
        response = await auth_client.get(f"/api/v1/executions/{uuid.uuid4()}/retry-from-failure-preview")

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
class TestRetryExecution:
    """Integration tests for POST /executions/{execution_id}/retry-from-failure."""

    async def test_retry_success(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "pending"
        assert data["retried_from_execution_id"] == str(execution.id)
        assert_user_reference(data["created_by"], test_user)
        version_result = await test_db_session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        assert data["workflow_version_id"] == str(version_result.one())

        mock_temporal_service.start_workflow.assert_called_once()
        _, kwargs = mock_temporal_service.start_workflow.call_args
        assert kwargs["workflow_metadata"]["retry"]["retry_from_execution_id"] == str(execution.id)
        assert kwargs["workflow_metadata"]["retry"]["failure_point_ids"] == ["step_2"]

    async def test_retry_uses_retained_version_not_current(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """SDP R10: retry runs the version retained from the original run, never a later save."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        original_version_id = execution.workflow_version_id
        changed = [
            dict(node, parameters={"code": "exit 0"}) if node["id"] == "step_1" else node for node in GRAPH_NODES
        ]
        await _save_new_version(test_db_session, test_workflow, test_user, changed)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["workflow_version_id"] == str(original_version_id)

        mock_temporal_service.start_workflow.assert_called_once()
        _, kwargs = mock_temporal_service.start_workflow.call_args
        retryed_step_1 = next(node for node in kwargs["workflow_def"]["nodes"] if node["id"] == "step_1")
        assert retryed_step_1["parameters"]["code"] == "echo hi"

    async def test_retry_rejected_state_returns_409(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        execution.status = ExecutionStatus.RUNNING
        test_db_session.add(execution)
        await test_db_session.commit()

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Execution Not Retryable From Failure",
            detail=data["detail"],
            code="EXECUTION_NOT_RETRYABLE_FROM_FAILURE",
            retryable=False,
        )

    async def test_retry_missing_execution_returns_404(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            f"/api/v1/executions/{uuid.uuid4()}/retry-from-failure",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_retry_carries_input_parameter_overrides_to_temporal(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """SDP AC-14/R10c: validated overrides reach the engine; plain retries carry none."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"], "input_parameter_overrides": {"step_2": {"code": "echo fixed"}}},
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_temporal_service.start_workflow.assert_called_once()
        _, kwargs = mock_temporal_service.start_workflow.call_args
        retry_ctx = kwargs["workflow_metadata"]["retry"]
        assert retry_ctx["failure_point_ids"] == ["step_2"]
        assert retry_ctx["input_parameter_overrides"] == {"step_2": {"code": "echo fixed"}}
        # The definition itself is untouched: the retry still runs the retained nodes.
        restarted_step_2 = next(n for n in kwargs["workflow_def"]["nodes"] if n["id"] == "step_2")
        assert restarted_step_2["parameters"]["code"] == "exit 1"

    async def test_retry_rejects_override_with_unknown_parameter_returns_409(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """AC-14: input keys must not change, so an unknown key is rejected, not silently added."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"], "input_parameter_overrides": {"step_2": {"nope": "x"}}},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "EXECUTION_NOT_RETRYABLE_FROM_FAILURE"
        assert "nope" in data["detail"]

    async def test_retry_without_overrides_sends_empty_override_map(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
        test_workflow: Workflow,
        mock_temporal_service: Mock,
    ) -> None:
        """The key is always present so the engine does not need a None branch."""
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_201_CREATED
        _, kwargs = mock_temporal_service.start_workflow.call_args
        assert kwargs["workflow_metadata"]["retry"]["input_parameter_overrides"] == {}

    async def test_retry_rejects_unknown_failure_point_returns_409(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """Only the retry endpoint accepts a selection, so it owns selection validation.

        The preview takes no selection and therefore cannot reject an unknown point; that
        check lives here, where a caller can actually supply one.
        """
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_3"]},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "EXECUTION_NOT_RETRYABLE_FROM_FAILURE"
        assert "step_3" in data["detail"]

    async def test_retry_rejects_explicit_selection_downstream_of_sanitized_returns_409(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """SDP AC-15/R9a explicit path: naming a point downstream of a sanitized step rejects.

        The default selection auto-includes the sanitized step instead (covered by
        test_preview_default_selection_auto_includes_sanitized_dependency), so this explicit
        rejection can only be exercised through the retry endpoint.
        """
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)
        await _add_completed_activity(test_db_session, execution, "step_1", {"token": "[REDACTED]", "stderr": ""})
        result = await test_db_session.exec(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == test_workflow.id,
                WorkflowVersion.version == test_workflow.current_version,
            )
        )
        version = result.one()
        definition = dict(version.workflow_definition)
        definition["nodes"] = [
            dict(node, parameters={**node.get("parameters", {}), "input_ref": "${step_1.token}"})
            if node.get("id") == "step_2"
            else node
            for node in definition.get("nodes", [])
        ]
        version.workflow_definition = definition
        test_db_session.add(version)
        await test_db_session.commit()

        response = await auth_client.post(
            f"/api/v1/executions/{execution.id}/retry-from-failure",
            json={"failure_point_ids": ["step_2"]},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["code"] == "EXECUTION_NOT_RETRYABLE_FROM_FAILURE"
        assert "step_1" in data["detail"]

    async def test_preview_rejects_a_body(
        self, auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_workflow: Workflow
    ) -> None:
        """The preview takes no selection: a supplied one is ignored, never honoured.

        Locks in that a GET carries no failure-point input, so the endpoint can never be
        coerced into validating a subset whose re-run count it did not compute.
        """
        execution = await _eligible_execution(test_db_session, test_workflow, test_user)

        response = await auth_client.get(
            f"/api/v1/executions/{execution.id}/retry-from-failure-preview",
            params={"failure_point_ids": "step_3"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # The unknown point in the query string is not a selection, so eligibility is unaffected
        # and the reported set is still the default (all currently failed nodes).
        assert data["eligible"] is True
        assert data["failure_point_ids"] == ["step_2"]
