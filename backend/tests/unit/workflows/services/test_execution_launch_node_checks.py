"""ExecutionService applies the launch gate before starting Temporal."""

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.metrics.types import ComponentLabel
from syntara.workflows.exceptions import TemporalUnavailableError, WorkflowLaunchRejectedError
from syntara.workflows.models.execution import ExecutionStatus
from syntara.workflows.node_launch_checks import WorkflowLaunchRejection
from syntara.workflows.services.execution_service import ExecutionService

_MODULE = "syntara.workflows.services.execution_service"
CALLER_ID = UUID("11111111-1111-4111-8111-111111111111")
WEBHOOK_SA_ID = UUID("22222222-2222-4222-8222-222222222222")


def _service() -> Any:  # noqa: ANN401
    service = cast("Any", ExecutionService.__new__(ExecutionService))
    service.session = MagicMock()
    service.session.add = MagicMock()
    service.session.commit = AsyncMock()
    service.user = SimpleNamespace(id=CALLER_ID, display_name="caller")
    service.temporal_service = MagicMock()
    service.temporal_service.start_workflow = AsyncMock()
    service.authz_evaluator = MagicMock()
    return service


def _workflow() -> Any:  # noqa: ANN401
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        name="wf",
        created_by=CALLER_ID,
        is_builtin=False,
        published_version_id=uuid4(),
    )


def _version(trigger_type: str = "manual_trigger") -> Any:  # noqa: ANN401
    return SimpleNamespace(
        id=uuid4(),
        version=3,
        schema_version="2.0.0",
        published_version_id=uuid4(),
        workflow_definition={
            "triggers": [{"id": "trigger", "type": trigger_type}],
            "nodes": [{"id": "step", "type": "script"}],
        },
    )


def _rejection() -> WorkflowLaunchRejection:
    return WorkflowLaunchRejection(
        reason="step_type_denied",
        principal_id=CALLER_ID,
        project_id=uuid4(),
        trigger_type="manual_trigger",
        denied_steps=[{"node_id": "step", "kind": "script", "denied_by": "deny-script"}],
    )


@pytest.mark.asyncio
async def test_interactive_rejection_returns_403_without_temporal_or_execution_record() -> None:
    service = _service()
    workflow = _workflow()
    rejection = _rejection()
    with (
        patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(max_concurrent_workflows=0)),
        patch(f"{_MODULE}.resolve_user_display_name", AsyncMock(return_value="author")),
        patch(f"{_MODULE}.build_workflow_metadata", return_value={}),
        patch(f"{_MODULE}.check_workflow_launch", AsyncMock(return_value=rejection)) as gate,
        pytest.raises(WorkflowLaunchRejectedError) as exc_info,
    ):
        await service._start_temporal_and_create_execution(
            workflow=workflow,
            workflow_version=_version(),
            input_data={},
            trigger_node_id="trigger",
            recorder=MagicMock(),
            component=ComponentLabel.EXECUTION_SERVICE,
        )

    assert exc_info.value.rejection is rejection
    assert exc_info.value.execution_id is None
    gate.assert_awaited_once()
    service.temporal_service.start_workflow.assert_not_awaited()
    service.session.add.assert_not_called()


@pytest.mark.asyncio
async def test_authorized_webhook_with_temporal_unavailable_is_checked_then_returns_503() -> None:
    service = _service()
    service.temporal_service = None
    with (
        patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(max_concurrent_workflows=0)),
        patch(f"{_MODULE}.resolve_user_display_name", AsyncMock(return_value="author")),
        patch(f"{_MODULE}.build_workflow_metadata", return_value={}),
        patch(f"{_MODULE}.check_workflow_launch", AsyncMock(return_value=None)) as gate,
        pytest.raises(TemporalUnavailableError),
    ):
        await service._start_temporal_and_create_execution(
            workflow=_workflow(),
            workflow_version=_version("webhook_trigger"),
            input_data={},
            trigger_node_id="trigger",
            recorder=MagicMock(),
            component=ComponentLabel.EXECUTION_SERVICE,
            launch_principal_id=WEBHOOK_SA_ID,
            persist_rejection=True,
            require_temporal=True,
        )

    gate.assert_awaited_once()
    service.session.add.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_rejection_persists_failed_execution_for_bound_service_account() -> None:
    service = _service()
    service.temporal_service = None
    workflow = _workflow()
    rejection = WorkflowLaunchRejection(
        reason="execution_run_denied",
        principal_id=WEBHOOK_SA_ID,
        project_id=workflow.project_id,
        trigger_type="webhook_trigger",
        denied_steps=[],
        denied_by="no-run",
    )
    with (
        patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(max_concurrent_workflows=0)),
        patch(f"{_MODULE}.resolve_user_display_name", AsyncMock(return_value="author")),
        patch(f"{_MODULE}.build_workflow_metadata", return_value={}),
        patch(f"{_MODULE}.check_workflow_launch", AsyncMock(return_value=rejection)) as gate,
        pytest.raises(WorkflowLaunchRejectedError) as exc_info,
    ):
        await service._start_temporal_and_create_execution(
            workflow=workflow,
            workflow_version=_version("webhook_trigger"),
            input_data={"event": True},
            trigger_node_id="trigger",
            recorder=MagicMock(),
            component=ComponentLabel.EXECUTION_SERVICE,
            launch_principal_id=WEBHOOK_SA_ID,
            persist_rejection=True,
        )

    rejected_execution = service.session.add.call_args.args[0]
    assert exc_info.value.execution_id == rejected_execution.id
    assert rejected_execution.status == ExecutionStatus.FAILED
    assert rejected_execution.completed_at is not None
    assert rejected_execution.created_by == WEBHOOK_SA_ID
    assert json.loads(rejected_execution.error_details) == rejection.to_dict()
    assert gate.await_args is not None
    assert gate.await_args.kwargs["principal_id"] == WEBHOOK_SA_ID
    service.session.commit.assert_awaited_once()
    assert service.temporal_service is None


@pytest.mark.asyncio
async def test_api_retry_uses_current_caller_even_for_a_webhook_trigger() -> None:
    service = _service()
    workflow = _workflow()
    with (
        patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(max_concurrent_workflows=0)),
        patch(f"{_MODULE}.resolve_user_display_name", AsyncMock(return_value="author")),
        patch(f"{_MODULE}.build_workflow_metadata", return_value={}),
        patch(f"{_MODULE}.check_workflow_launch", AsyncMock(return_value=_rejection())) as gate,
        pytest.raises(WorkflowLaunchRejectedError),
    ):
        await service._start_temporal_and_create_execution(
            workflow=workflow,
            workflow_version=_version("webhook_trigger"),
            input_data={},
            trigger_node_id="trigger",
            recorder=MagicMock(),
            component=ComponentLabel.EXECUTION_SERVICE,
            retried_from_execution_id=uuid4(),
        )

    assert gate.await_args is not None
    assert gate.await_args.kwargs["principal_id"] == CALLER_ID


@pytest.mark.asyncio
async def test_test_execution_uses_invoker_and_checks_the_full_definition() -> None:
    service = _service()
    workflow = _workflow()
    workflow.name = "wf"
    version = _version()
    query_result = MagicMock()
    query_result.first.return_value = (workflow, version)
    service.session.exec = AsyncMock(return_value=query_result)
    rejection = _rejection()
    with (
        patch(f"{_MODULE}.get_metrics_recorder", return_value=MagicMock()),
        patch(f"{_MODULE}.resolve_user_display_name", AsyncMock(return_value="author")),
        patch(f"{_MODULE}.build_workflow_metadata", return_value={}),
        patch(f"{_MODULE}.check_workflow_launch", AsyncMock(return_value=rejection)) as gate,
        pytest.raises(WorkflowLaunchRejectedError),
    ):
        await service.create_test_execution(
            workflow_id=workflow.id,
            target_node_id="step",
            pre_resolved_nodes={},
            trigger_inputs={},
            execute_target=True,
            trigger_node_id="trigger",
        )

    assert gate.await_args is not None
    assert gate.await_args.kwargs["definition"] is version.workflow_definition
    assert gate.await_args.kwargs["principal_id"] == CALLER_ID
    service.session.add.assert_not_called()
    service.temporal_service.start_workflow.assert_not_awaited()
