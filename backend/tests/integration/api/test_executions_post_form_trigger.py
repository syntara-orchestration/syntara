"""Integration coverage for Form Trigger submissions on execution and Run Step APIs."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from prometheus_client import CollectorRegistry
from sqlalchemy import func
from sqlmodel import select

from syntara.audit.outbox.worker import get_outbox_worker
from syntara.authz.engine import clear_authz_cache
from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import ComponentLabel, MetricType
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.responses import WorkflowStartResponse
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService
from tests.integration.helpers.error_data import assert_error_data

if TYPE_CHECKING:
    from collections.abc import Generator

    from fastapi import FastAPI
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.workflows.models.workflow import Workflow


@pytest.fixture
def mock_temporal_service(session_app: FastAPI) -> Generator[Mock, None, None]:
    """Override Temporal so API tests can inspect the normalized workflow input."""
    mock_service = Mock(spec=TemporalExecutionService)

    async def start_workflow(*_: object, **__: object) -> WorkflowStartResponse:
        execution_id = str(uuid.uuid4())
        return WorkflowStartResponse(
            execution_id=execution_id,
            workflow_id="wf-mock",
            temporal_workflow_id=f"temporal-{execution_id}",
            temporal_run_id=f"run-{execution_id}",
            status="RUNNING",
            started_at="2026-01-01T00:00:00Z",
        )

    mock_service.start_workflow = AsyncMock(side_effect=start_workflow)

    async def override_get_temporal_service() -> Mock:
        return mock_service

    session_app.dependency_overrides[get_temporal_execution_service] = override_get_temporal_service
    yield mock_service
    session_app.dependency_overrides.pop(get_temporal_execution_service, None)


async def _execution_count(session: AsyncSession, workflow_id: uuid.UUID) -> int:
    """Count executions associated with a workflow."""
    result = await session.exec(select(func.count()).select_from(Execution).where(Execution.workflow_id == workflow_id))
    return result.one()


def _valid_form_input() -> dict[str, Any]:
    """Return a valid submission that exercises coercion and normalization."""
    return {
        "required_text": "submitted",
        "count": "42",
        "start": {"date": "2026-02-14"},
        "contact": "Bob@Example.COM",
    }


def _cleaned_form_input() -> dict[str, Any]:
    """Return the expected normalized Form Trigger values."""
    return {
        "required_text": "submitted",
        "environment": None,
        "count": 42.0,
        "start": "2026-02-14",
        "contact": "Bob@example.com",
    }


@pytest.mark.asyncio
async def test_create_form_trigger_execution_persists_and_starts_with_cleaned_input(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """A valid form submission is normalized before Temporal and persistence."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": _valid_form_input(),
            "use_published": True,
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["input_data"] == _cleaned_form_input()
    mock_temporal_service.start_workflow.assert_awaited_once()
    assert mock_temporal_service.start_workflow.await_args.kwargs["input_data"] == _cleaned_form_input()

    result = await test_db_session.exec(select(Execution).where(Execution.id == uuid.UUID(data["id"])))
    execution = result.one()
    assert execution.input_data == _cleaned_form_input()
    assert execution.trigger_node_id == "form"
    assert execution.trigger_type == "form_trigger"
    assert execution.workflow_version_id == form_trigger_workflow.published_version_id


@pytest.mark.integration
@pytest.mark.asyncio
@patch("syntara.audit.outbox.worker._build_otel_log_record")
async def test_form_trigger_submission_emits_metadata_only_audit_event(
    mock_build_otel_log_record: MagicMock,
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
    test_user: User,
) -> None:
    """A committed submission reaches the audit export with bounded metadata only."""
    submitted = _valid_form_input()
    submitted["required_text"] = "FORM_TRIGGER_PRIVATE_TEXT_97126"
    submitted["count"] = "713"
    submitted["start"] = {"date": "2051-03-19"}
    submitted["contact"] = "private.user.97126@example.com"

    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": submitted,
            "use_published": True,
        },
    )

    assert response.status_code == 201, response.text
    execution_id = uuid.UUID(response.json()["id"])
    await get_outbox_worker().drain()

    events = [
        call.args[0]
        for call in mock_build_otel_log_record.call_args_list
        if call.args[0].event_action == "form_trigger_submitted"
    ]
    assert len(events) == 1
    event = events[0]
    assert event.workflow_id == form_trigger_workflow.id
    assert event.execution_id == execution_id
    assert event.activity_id == "form"
    assert event.actor_id == test_user.id
    assert event.structured_data.model_dump()["field_count"] == 5
    assert event.structured_data.model_dump()["field_types"] == ["date", "dropdown", "email", "number", "text"]
    exported_payload = event.model_dump_json()
    for submitted_value in (
        "FORM_TRIGGER_PRIVATE_TEXT_97126",
        "713",
        "2051-03-19",
        "private.user.97126@example.com",
    ):
        assert submitted_value not in exported_payload
    for field_label in ("Required text", "Environment", "Count", "Start", "Contact"):
        assert field_label not in exported_payload


@pytest.mark.integration
@pytest.mark.asyncio
async def test_form_trigger_submission_records_latency_metric(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """A committed form-trigger execution records its service-entry latency."""
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())
    with patch(
        "syntara.workflows.services.execution_service.get_metrics_recorder",
        return_value=recorder,
    ):
        response = await auth_client.post(
            "/api/v1/executions",
            json={
                "workflow_id": str(form_trigger_workflow.id),
                "trigger_node_id": "form",
                "input_data": _valid_form_input(),
                "use_published": True,
            },
        )

    assert response.status_code == 201, response.text
    records = list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START}))
    assert len(records) == 1
    assert records[0].unit == "ms"
    assert records[0].value >= 0
    assert records[0].labels == {"component": ComponentLabel.EXECUTION_SERVICE.value}
    mock_temporal_service.start_workflow.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_form_trigger_submission_does_not_record_latency_metric(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """A rejected form submission has no form-trigger latency observation."""
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())
    with patch(
        "syntara.workflows.services.execution_service.get_metrics_recorder",
        return_value=recorder,
    ):
        response = await auth_client.post(
            "/api/v1/executions",
            json={
                "workflow_id": str(form_trigger_workflow.id),
                "trigger_node_id": "form",
                "input_data": {"count": "42"},
                "use_published": True,
            },
        )

    assert response.status_code == 422
    assert list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START})) == []
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_form_trigger_submission_returns_422_without_starting_execution(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """Missing required fields fail before Temporal or an execution row is created."""
    count_before = await _execution_count(test_db_session, form_trigger_workflow.id)
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": {"count": "42", "start": {"date": "2026-02-14"}, "contact": "bob@example.com"},
            "use_published": True,
        },
    )

    assert response.status_code == 422
    assert_error_data(
        response,
        error_type=PROBLEM_TYPES["validation_error"],
        title="Form Validation Error",
        detail="Form validation failed: required_text: This field is required",
        code="FORM_VALIDATION_ERROR",
        retryable=False,
    )
    assert "errors" not in response.json()
    assert await _execution_count(test_db_session, form_trigger_workflow.id) == count_before
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("input_data", "error_fragment"),
    [
        ({**_valid_form_input(), "unknown": "value"}, "unknown: Unknown field"),
        ({**_valid_form_input(), "environment": "production"}, "environment: Selected value is not in the option list"),
    ],
    ids=["unknown-key", "option-membership"],
)
async def test_form_trigger_submission_reports_all_field_failures(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
    input_data: dict[str, Any],
    error_fragment: str,
) -> None:
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": input_data,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "FORM_VALIDATION_ERROR"
    assert error_fragment in response.json()["detail"]
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_form_trigger_submission_flattens_multiple_errors_in_field_order(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": {"count": "not-a-number", "unknown": "value"},
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.index("required_text: This field is required") < detail.index("count: Must be a valid number string")
    assert detail.index("count: Must be a valid number string") < detail.index("start: This field is required")
    assert detail.index("start: This field is required") < detail.index("contact: This field is required")
    assert detail.index("contact: This field is required") < detail.index("unknown: Unknown field")
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_trigger_keeps_input_schema_defaults_and_validation(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """Manual trigger behavior remains on the existing JSON Schema path."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "manual",
            "input_data": {"required_field": "provided"},
        },
    )

    assert response.status_code == 201, response.text
    expected_input = {"name": "manual-default", "required_field": "provided"}
    assert response.json()["input_data"] == expected_input
    assert mock_temporal_service.start_workflow.await_args.kwargs["input_data"] == expected_input

    invalid = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "manual",
            "input_data": {"required_field": 42},
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "TRIGGER_VALIDATION_ERROR"
    assert mock_temporal_service.start_workflow.await_count == 1

    unknown = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "unknown-trigger",
            "input_data": {},
        },
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "VALIDATION_ERROR"
    assert mock_temporal_service.start_workflow.await_count == 1


@pytest.mark.asyncio
async def test_form_trigger_run_permission_is_checked_before_submission_validation(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A denied caller receives 403 even when the submitted form is invalid."""
    denied_evaluator = Mock()
    denied_evaluator.evaluate.return_value = {"allow": False}
    monkeypatch.setattr(
        "syntara.workflows.executions_router.get_authz_evaluator",
        lambda _request: denied_evaluator,
    )
    clear_authz_cache()

    response = await auth_client.post(
        "/api/v1/executions",
        json={"workflow_id": str(form_trigger_workflow.id), "trigger_node_id": "form", "input_data": {}},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTHORIZATION_DENIED"
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_form_trigger_execution_keeps_input_data_size_limit(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """The existing JSONB limit rejects oversized input before workflow start."""
    response = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": {"large": "x" * (1024 * 1024 + 1)},
        },
    )

    assert response.status_code == 422
    assert "input_data exceeds maximum serialized size" in response.json()["detail"]
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_reuses_cleaned_form_submission_without_revalidation(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """Retry carries the original normalized input even if the form later changes."""
    created = await auth_client.post(
        "/api/v1/executions",
        json={
            "workflow_id": str(form_trigger_workflow.id),
            "trigger_node_id": "form",
            "input_data": _valid_form_input(),
        },
    )
    assert created.status_code == 201, created.text
    original_id = uuid.UUID(created.json()["id"])

    original_result = await test_db_session.exec(select(Execution).where(Execution.id == original_id))
    original = original_result.one()
    original.status = ExecutionStatus.FAILED

    version_result = await test_db_session.exec(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == form_trigger_workflow.id,
            WorkflowVersion.version == form_trigger_workflow.current_version,
        )
    )
    version = version_result.one()
    changed_definition = deepcopy(version.workflow_definition)
    form_trigger = next(trigger for trigger in changed_definition["triggers"] if trigger["id"] == "form")
    form_trigger["parameters"]["form_definition"]["fields"].append(
        {"type": "text", "value_name": "added_later", "label": "Added later", "required": True}
    )
    version.workflow_definition = changed_definition
    await test_db_session.commit()

    retried = await auth_client.post(f"/api/v1/executions/{original_id}/retry")

    assert retried.status_code == 201, retried.text
    retried_data = retried.json()
    assert retried_data["input_data"] == _cleaned_form_input()
    assert retried_data["retried_from_execution_id"] == str(original_id)
    assert mock_temporal_service.start_workflow.await_count == 2
    assert mock_temporal_service.start_workflow.await_args.kwargs["input_data"] == _cleaned_form_input()


@pytest.mark.asyncio
async def test_form_trigger_export_import_round_trip(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    form_trigger_workflow: Workflow,
    form_trigger_workflow_definition: dict[str, Any],
) -> None:
    """Form Trigger fields and form metadata survive workflow export and import."""
    exported = await auth_client.get(
        f"/api/v1/workflows/{form_trigger_workflow.id}/versions/{form_trigger_workflow.current_version}/export"
    )
    assert exported.status_code == 200, exported.text

    imported = await auth_client.post(
        "/api/v1/workflows",
        json={
            "name": f"imported-form-trigger-{uuid.uuid4().hex[:8]}",
            "description": "Imported Form Trigger validation fixture",
            "project_id": str(form_trigger_workflow.project_id),
            "workflow_definition": exported.json(),
        },
    )
    assert imported.status_code == 201, imported.text
    imported_data = imported.json()
    assert not imported_data.get("has_validation_issues", False)

    imported_version = await test_db_session.exec(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == uuid.UUID(imported_data["id"]),
            WorkflowVersion.version == imported_data["current_version"],
        )
    )
    imported_definition = imported_version.one().workflow_definition
    original_form_parameters = next(
        trigger["parameters"] for trigger in form_trigger_workflow_definition["triggers"] if trigger["id"] == "form"
    )
    imported_form_parameters = next(
        trigger["parameters"] for trigger in imported_definition["triggers"] if trigger["id"] == "form"
    )
    assert imported_form_parameters == original_form_parameters


@pytest.mark.asyncio
async def test_run_step_form_trigger_passes_cleaned_inputs_to_temporal(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """Run Step normalizes trigger inputs even though the trigger is not its target."""
    response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "form_target",
            "pre_resolved_nodes": {},
            "trigger_inputs": _valid_form_input(),
            "trigger_node_id": "form",
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["input_data"] == _cleaned_form_input()
    assert mock_temporal_service.start_workflow.await_args.kwargs["input_data"] == _cleaned_form_input()
    assert mock_temporal_service.start_workflow.await_args.kwargs["trigger_node_id"] == "form"

    result = await test_db_session.exec(select(Execution).where(Execution.id == uuid.UUID(data["id"])))
    assert result.one().input_data == _cleaned_form_input()


@pytest.mark.asyncio
async def test_run_step_rejects_missing_required_form_input_before_temporal(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    count_before = await _execution_count(test_db_session, form_trigger_workflow.id)
    response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "form_target",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "form",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "FORM_VALIDATION_ERROR"
    assert "required_text: This field is required" in response.json()["detail"]
    assert await _execution_count(test_db_session, form_trigger_workflow.id) == count_before
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trigger_inputs", "error_fragment"),
    [
        ({**_valid_form_input(), "extra": "unknown"}, "extra: Unknown field"),
        ({**_valid_form_input(), "environment": "production"}, "environment: Selected value is not in the option list"),
    ],
    ids=["unknown-key", "invalid-option"],
)
async def test_run_step_rejects_invalid_form_fields(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
    trigger_inputs: dict[str, Any],
    error_fragment: str,
) -> None:
    response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "form_target",
            "pre_resolved_nodes": {},
            "trigger_inputs": trigger_inputs,
            "trigger_node_id": "form",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "FORM_VALIDATION_ERROR"
    assert error_fragment in response.json()["detail"]
    mock_temporal_service.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_step_leaves_manual_trigger_input_schema_unvalidated(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """The form-trigger branch does not change existing manual Run Step behavior."""
    response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "manual_target",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "manual",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["input_data"] == {}
    assert mock_temporal_service.start_workflow.await_args.kwargs["input_data"] == {}


@pytest.mark.asyncio
async def test_run_step_unknown_trigger_id_keeps_existing_service_behavior(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """An unknown trigger ID is not newly rejected by the validation hook."""
    response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "form_target",
            "pre_resolved_nodes": {},
            "trigger_inputs": {},
            "trigger_node_id": "unknown-trigger",
        },
    )

    assert response.status_code == 201, response.text
    mock_temporal_service.start_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_step_still_rejects_trigger_target_and_pre_resolved_trigger(
    auth_client: AsyncClient,
    form_trigger_workflow: Workflow,
    mock_temporal_service: Mock,
) -> None:
    """Form validation does not make a trigger a test target or mockable predecessor."""
    target_response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "form",
            "pre_resolved_nodes": {},
            "trigger_inputs": _valid_form_input(),
            "trigger_node_id": "form",
        },
    )
    assert target_response.status_code == 422
    assert "trigger nodes are not valid test targets" in target_response.json()["detail"]

    pre_resolved_response = await auth_client.post(
        f"/api/v1/workflows/{form_trigger_workflow.id}/test",
        json={
            "target_node_id": "form_target",
            "pre_resolved_nodes": {"form": {"output": {"response_data": {"required_text": "mocked"}}}},
            "trigger_inputs": _valid_form_input(),
            "trigger_node_id": "form",
        },
    )
    assert pre_resolved_response.status_code == 422
    assert "trigger nodes cannot be pre-resolved" in pre_resolved_response.json()["detail"]
    mock_temporal_service.start_workflow.assert_not_awaited()
