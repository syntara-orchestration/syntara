"""Unit tests for Form Trigger submission validation in the execution service."""

import inspect
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from prometheus_client import CollectorRegistry
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.forms.exceptions import FormDataValidationError
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType
from syntara.workflows.audit.form_trigger import FormTriggerSubmittedEvent
from syntara.workflows.exceptions import TriggerValidationError
from syntara.workflows.form_trigger import (
    record_form_trigger_submission as _real_record_form_trigger_submission,
)
from syntara.workflows.form_trigger import (
    validate_form_trigger_submission,
)
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService


def _field(field_type: str, value_name: str, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build one raw form-field definition."""
    return {"type": field_type, "value_name": value_name, "label": value_name.replace("_", " ").title(), **overrides}


def _form_trigger(*fields: dict[str, Any], node_id: str = "form") -> dict[str, Any]:
    """Build a raw Form Trigger node."""
    return {
        "id": node_id,
        "type": "form_trigger",
        "parameters": {"form_definition": {"fields": list(fields)}},
    }


def test_start_temporal_and_create_execution_has_no_form_specific_parameters() -> None:
    parameters = inspect.signature(ExecutionService._start_temporal_and_create_execution).parameters

    assert not [name for name in parameters if "form" in name]


class TestTriggerInputDispatch:
    """Form triggers use form validation; other triggers retain JSON Schema behavior."""

    def test_form_trigger_dispatches_to_form_submission_validator(self) -> None:
        trigger = _form_trigger(_field("number", "count"))
        submitted = {"count": "42"}

        normalized = ExecutionService._normalize_trigger_input(trigger, submitted)

        assert normalized.input_data == {"count": 42.0}
        assert normalized.form_schema is not None
        assert normalized.form_schema.field_types == ["number"]
        assert normalized.form_schema.field_count == 1
        assert submitted == {"count": "42"}

    def test_manual_trigger_keeps_json_schema_defaults_in_place(self) -> None:
        trigger = {
            "id": "manual",
            "type": "manual_trigger",
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "default": "default-name"}},
                }
            },
        }
        submitted: dict[str, Any] = {}

        normalized = ExecutionService._normalize_trigger_input(trigger, submitted)

        assert normalized.input_data is submitted
        assert normalized.form_schema is None
        assert submitted == {"name": "default-name"}

    @pytest.mark.parametrize("trigger_type", ["manual_trigger", "webhook_trigger", "eda_trigger"])
    def test_non_form_trigger_without_schema_is_unchanged(self, trigger_type: str) -> None:
        submitted = {"untouched": "value"}

        normalized = ExecutionService._normalize_trigger_input(
            {"id": "trigger", "type": trigger_type, "parameters": {}},
            submitted,
        )

        assert normalized.input_data is submitted
        assert normalized.form_schema is None
        assert submitted == {"untouched": "value"}

    def test_form_submission_helper_returns_cleaned_data(self) -> None:
        trigger = _form_trigger(_field("text", "name"))

        cleaned_input, form_schema = validate_form_trigger_submission(trigger, {"name": "Ada"})

        assert cleaned_input == {"name": "Ada"}
        assert form_schema.field_types == ["text"]
        assert form_schema.field_count == 1


class TestFormTriggerSubmissionCleaning:
    """Form Trigger values use the same coercion and defaults as form prompts."""

    def test_number_is_coerced_and_email_domain_normalized(self) -> None:
        trigger = _form_trigger(_field("number", "count"), _field("email", "contact"))

        cleaned_input, form_schema = validate_form_trigger_submission(
            trigger,
            {"count": "42", "contact": "Bob@Example.COM"},
        )

        assert cleaned_input == {"count": 42.0, "contact": "Bob@example.com"}
        assert form_schema.field_types == ["email", "number"]

    def test_optional_absent_field_is_omitted(self) -> None:
        trigger = _form_trigger(_field("text", "required", required=True), _field("text", "optional"))

        cleaned_input, form_schema = validate_form_trigger_submission(trigger, {"required": "value"})

        assert cleaned_input == {"required": "value"}
        assert form_schema.field_types == ["text"]
        assert form_schema.field_count == 2

    def test_field_count_uses_all_configured_fields_when_values_are_omitted(self) -> None:
        fields = (
            _field("text", "required", required=True),
            *(_field("text", f"optional_{index}") for index in range(9)),
        )
        trigger = _form_trigger(*fields)

        cleaned_input, form_schema = validate_form_trigger_submission(trigger, {"required": "value"})

        assert len(cleaned_input) == 1
        assert form_schema.field_count == 10
        assert form_schema.field_types == ["text"]

    def test_default_is_applied(self) -> None:
        trigger = _form_trigger(_field("text", "name", default="Ada"))

        cleaned_input, form_schema = validate_form_trigger_submission(trigger, {})

        assert cleaned_input == {"name": "Ada"}
        assert form_schema.field_types == ["text"]
        assert form_schema.field_count == 1

    def test_date_is_normalized_to_iso_string(self) -> None:
        trigger = _form_trigger(_field("date", "start"))

        cleaned_input, form_schema = validate_form_trigger_submission(trigger, {"start": {"date": "2026-02-14"}})

        assert cleaned_input == {"start": "2026-02-14"}
        assert form_schema.field_types == ["date"]
        assert form_schema.field_count == 1

    def test_checkbox_on_is_coerced_to_true(self) -> None:
        trigger = _form_trigger(_field("checkbox", "confirmed"))

        cleaned_input, form_schema = validate_form_trigger_submission(trigger, {"confirmed": "on"})

        assert cleaned_input == {"confirmed": True}
        assert form_schema.field_types == ["checkbox"]

    def test_submission_input_is_not_mutated(self) -> None:
        trigger = _form_trigger(_field("text", "name"), _field("text", "defaulted", default="default"))
        submitted = {"name": "Ada"}

        validate_form_trigger_submission(trigger, submitted)

        assert submitted == {"name": "Ada"}


class TestFormTriggerSubmissionFailures:
    """Form data errors retain field details and identify their trigger."""

    def test_missing_required_field_has_trigger_context(self) -> None:
        trigger = _form_trigger(_field("text", "name", required=True), node_id="request")

        with pytest.raises(FormDataValidationError) as exc_info:
            validate_form_trigger_submission(trigger, {})

        assert [(error.field, error.code) for error in exc_info.value.errors] == [("name", "required")]
        assert exc_info.value.form_id == "request"

    @pytest.mark.parametrize(
        ("fields", "submitted", "expected_code"),
        [
            ((_field("text", "name"),), {"name": "Ada", "unknown": "value"}, "unknown_field"),
            (
                (
                    _field(
                        "dropdown",
                        "environment",
                        options={
                            "source": "static",
                            "values": [{"display_label": "Staging", "value": "staging"}],
                        },
                    ),
                ),
                {"environment": "production"},
                "not_in_options",
            ),
            ((_field("number", "count"),), {"count": {"bad": "value"}}, "type"),
            ((_field("email", "contact"),), {"contact": "not-an-email"}, "invalid_format"),
        ],
        ids=["unknown-key", "invalid-option", "wrong-type", "invalid-email"],
    )
    def test_invalid_field_data_is_rejected(
        self,
        fields: tuple[dict[str, Any], ...],
        submitted: dict[str, Any],
        expected_code: str,
    ) -> None:
        trigger = _form_trigger(*fields)

        with pytest.raises(FormDataValidationError) as exc_info:
            validate_form_trigger_submission(trigger, submitted)

        assert expected_code in {error.code for error in exc_info.value.errors}

    def test_all_field_errors_are_preserved(self) -> None:
        trigger = _form_trigger(
            _field("text", "required_name", required=True),
            _field("number", "count", required=True),
        )

        with pytest.raises(FormDataValidationError) as exc_info:
            validate_form_trigger_submission(trigger, {"count": "not-a-number", "unknown": 1})

        assert {(error.field, error.code) for error in exc_info.value.errors} == {
            ("required_name", "required"),
            ("count", "type"),
            ("unknown", "unknown_field"),
        }

    @pytest.mark.parametrize(
        "trigger",
        [
            {"id": "form", "type": "form_trigger"},
            {"id": "form", "type": "form_trigger", "parameters": {}},
            {"id": "form", "type": "form_trigger", "parameters": {"form_definition": {"fields": []}}},
            {
                "id": "form",
                "type": "form_trigger",
                "parameters": {"form_definition": {"fields": [{"type": "unknown", "value_name": "x"}]}},
            },
        ],
        ids=["missing-parameters", "missing-definition", "empty-fields", "invalid-field-type"],
    )
    def test_invalid_stored_definition_is_a_trigger_validation_error(self, trigger: dict[str, Any]) -> None:
        with pytest.raises(TriggerValidationError, match="form definition"):
            validate_form_trigger_submission(trigger, {})

    def test_dynamic_options_are_rejected_for_form_triggers(self) -> None:
        trigger = _form_trigger(
            _field(
                "dropdown",
                "environment",
                options={
                    "source": "dynamic",
                    "expression": "${upstream.options}",
                    "label_key": "label",
                    "value_key": "value",
                },
            )
        )

        with pytest.raises(TriggerValidationError, match="form definition"):
            validate_form_trigger_submission(trigger, {"environment": "staging"})

    def test_wrong_typed_default_is_a_trigger_validation_error(self) -> None:
        trigger = _form_trigger(_field("number", "count", default="not-a-number"))

        with pytest.raises(TriggerValidationError, match="form definition"):
            validate_form_trigger_submission(trigger, {})


def _service_for_execution(trigger_node: dict[str, Any]) -> tuple[ExecutionService, Mock, Mock]:
    """Build an execution service whose workflow query returns the supplied trigger."""
    workflow_id = uuid4()
    workflow = Mock(spec=Workflow)
    workflow.id = workflow_id
    workflow.name = "form-trigger-test"
    workflow.project_id = uuid4()
    workflow.is_builtin = False
    workflow.current_version = 1
    workflow.published_version_id = uuid4()
    workflow.created_by = uuid4()

    workflow_version = Mock(spec=WorkflowVersion)
    workflow_version.id = uuid4()
    workflow_version.version = 1
    workflow_version.schema_version = "2.0.0"
    workflow_version.workflow_definition = {
        "schema_version": "2.0.0",
        "triggers": [trigger_node],
        "nodes": [{"id": "target", "type": "script"}],
        "edges": [],
    }

    query_result = Mock()
    query_result.first.return_value = (workflow, workflow_version)
    session = Mock(spec=AsyncSession)
    session.exec = AsyncMock(return_value=query_result)
    session.add = Mock()
    session.commit = AsyncMock()

    user = Mock(spec=User)
    user.id = uuid4()
    user.display_name = "Form Trigger Tester"
    service = ExecutionService(session=session, user=user)
    return service, session, workflow


def _temporal_service() -> tuple[Mock, UUID]:
    """Build a Temporal mock that starts a workflow and returns its execution ID."""
    execution_id = uuid4()
    temporal_result = Mock(
        execution_id=str(execution_id),
        temporal_workflow_id=f"temporal-{execution_id}",
        temporal_run_id="run-1",
    )
    temporal_service = Mock()
    temporal_service.start_workflow = AsyncMock(return_value=temporal_result)
    temporal_service.cancel_workflow = AsyncMock()
    return temporal_service, execution_id


@pytest.mark.asyncio
async def test_create_execution_dispatches_metadata_and_records_metric() -> None:
    trigger = _form_trigger(
        _field("text", "name", required=True),
        _field("text", "optional"),
        _field("number", "defaulted", default=7),
        node_id="form-start",
    )
    service, session, workflow = _service_for_execution(trigger)
    temporal_service, execution_id = _temporal_service()
    service.temporal_service = temporal_service
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())
    read_model = Mock(id=execution_id)
    call_order = Mock()
    call_order.attach_mock(session.commit, "commit")

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch(
            "syntara.workflows.services.execution_service.get_settings",
            return_value=Mock(max_concurrent_workflows=0),
        ),
        patch(
            "syntara.workflows.services.execution_service.resolve_user_display_name",
            new_callable=AsyncMock,
            return_value="Workflow Author",
        ),
        patch.object(service, "_to_read", new_callable=AsyncMock, return_value=read_model) as to_read,
        patch(
            "syntara.workflows.services.execution_service.record_form_trigger_submission",
            wraps=_real_record_form_trigger_submission,
        ) as submission_record,
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        call_order.attach_mock(to_read, "read_model")
        call_order.attach_mock(submission_record, "record_submission")
        result = await service.create_execution(
            workflow.id,
            {"name": "Ada"},
            "form-start",
        )

    assert result is read_model
    session.commit.assert_awaited_once()
    temporal_service.start_workflow.assert_awaited_once()
    submission_record.assert_called_once()
    call_names = [entry[0] for entry in call_order.mock_calls]
    assert call_names.index("commit") < call_names.index("read_model") < call_names.index("record_submission")

    form_events = [
        call.args[0] for call in dispatch.call_args_list if isinstance(call.args[0], FormTriggerSubmittedEvent)
    ]
    assert len(form_events) == 1
    event = form_events[0]
    assert event.workflow_id == workflow.id
    assert event.workflow_name == workflow.name
    assert event.execution_id == execution_id
    assert event.trigger_node_id == "form-start"
    assert event.submitted_by == service.user.id
    assert event.field_count == 3
    assert event.field_types == ["number", "text"]

    records = list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START}))
    assert len(records) == 1
    assert records[0].unit == "ms"
    assert records[0].value >= 0
    assert records[0].labels == {"component": "execution_service"}


@pytest.mark.asyncio
async def test_create_execution_does_not_instrument_non_form_trigger() -> None:
    trigger = {"id": "manual", "type": "manual_trigger", "parameters": {}}
    service, _, workflow = _service_for_execution(trigger)
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch.object(
            service,
            "_start_temporal_and_create_execution",
            new_callable=AsyncMock,
            return_value=Mock(id=uuid4()),
        ),
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        await service.create_execution(workflow.id, {}, "manual")

    dispatch.assert_not_called()
    assert list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START})) == []


@pytest.mark.asyncio
async def test_create_execution_does_not_instrument_invalid_form_submission() -> None:
    trigger = _form_trigger(_field("text", "required", required=True))
    service, _, workflow = _service_for_execution(trigger)
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch.object(
            service,
            "_start_temporal_and_create_execution",
            new_callable=AsyncMock,
        ) as start_execution,
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        with pytest.raises(FormDataValidationError):
            await service.create_execution(workflow.id, {}, "form")

    start_execution.assert_not_awaited()
    dispatch.assert_not_called()
    assert list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START})) == []


@pytest.mark.asyncio
async def test_create_execution_does_not_instrument_when_temporal_start_fails() -> None:
    trigger = _form_trigger(_field("text", "name", required=True))
    service, session, workflow = _service_for_execution(trigger)
    temporal_service, _ = _temporal_service()
    temporal_service.start_workflow.side_effect = RuntimeError("Temporal unavailable")
    service.temporal_service = temporal_service
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch(
            "syntara.workflows.services.execution_service.get_settings",
            return_value=Mock(max_concurrent_workflows=0),
        ),
        patch(
            "syntara.workflows.services.execution_service.resolve_user_display_name",
            new_callable=AsyncMock,
            return_value="Workflow Author",
        ),
        patch(
            "syntara.workflows.services.execution_service.record_form_trigger_submission",
            wraps=_real_record_form_trigger_submission,
        ) as submission_record,
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        with pytest.raises(RuntimeError, match="Temporal unavailable"):
            await service.create_execution(workflow.id, {"name": "Ada"}, "form")

    temporal_service.start_workflow.assert_awaited_once()
    session.commit.assert_not_awaited()
    submission_record.assert_not_called()
    assert not any(isinstance(call.args[0], FormTriggerSubmittedEvent) for call in dispatch.call_args_list)
    assert list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START})) == []


@pytest.mark.asyncio
async def test_create_execution_does_not_instrument_when_commit_fails() -> None:
    trigger = _form_trigger(_field("text", "name", required=True))
    service, session, workflow = _service_for_execution(trigger)
    temporal_service, _ = _temporal_service()
    service.temporal_service = temporal_service
    session.commit = AsyncMock(side_effect=RuntimeError("DB commit failed"))
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch(
            "syntara.workflows.services.execution_service.get_settings",
            return_value=Mock(max_concurrent_workflows=0),
        ),
        patch(
            "syntara.workflows.services.execution_service.resolve_user_display_name",
            new_callable=AsyncMock,
            return_value="Workflow Author",
        ),
        patch(
            "syntara.workflows.services.execution_service.record_form_trigger_submission",
            wraps=_real_record_form_trigger_submission,
        ) as submission_record,
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        with pytest.raises(RuntimeError, match="DB commit failed"):
            await service.create_execution(workflow.id, {"name": "Ada"}, "form")

    temporal_service.start_workflow.assert_awaited_once()
    temporal_service.cancel_workflow.assert_awaited_once()
    session.commit.assert_awaited_once()
    submission_record.assert_not_called()
    assert not any(isinstance(call.args[0], FormTriggerSubmittedEvent) for call in dispatch.call_args_list)
    assert list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START})) == []


@pytest.mark.asyncio
async def test_metric_recording_failure_does_not_fail_form_trigger_execution() -> None:
    trigger = _form_trigger(_field("text", "name", required=True))
    service, session, workflow = _service_for_execution(trigger)
    read_model = Mock(id=uuid4())
    recorder = Mock()
    recorder.record.side_effect = [None, RuntimeError("metrics unavailable")]

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch(
            "syntara.workflows.services.execution_service.get_settings",
            return_value=Mock(max_concurrent_workflows=0),
        ),
        patch(
            "syntara.workflows.services.execution_service.resolve_user_display_name",
            new_callable=AsyncMock,
            return_value="Workflow Author",
        ),
        patch.object(service, "_to_read", new_callable=AsyncMock, return_value=read_model),
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        result = await service.create_execution(workflow.id, {"name": "Ada"}, "form")

    assert result is read_model
    session.commit.assert_awaited_once()
    assert recorder.record.call_count == 2
    assert recorder.record.call_args_list[0].args[0] is MetricType.WORKFLOW_STATUS
    metric_args, metric_kwargs = recorder.record.call_args_list[1]
    assert metric_args[0] is MetricType.FORM_TRIGGER_SUBMISSION_START
    assert isinstance(metric_args[1], float)
    assert metric_kwargs == {"unit": "ms", "component": "execution_service"}
    form_events = [
        call.args[0] for call in dispatch.call_args_list if isinstance(call.args[0], FormTriggerSubmittedEvent)
    ]
    assert len(form_events) == 1


@pytest.mark.asyncio
async def test_create_test_execution_validates_form_without_form_trigger_observability() -> None:
    trigger = _form_trigger(_field("text", "name", required=True))
    service, session, workflow = _service_for_execution(trigger)
    recorder = MetricsRecorder(prometheus_registry=CollectorRegistry())

    with (
        patch("syntara.workflows.services.execution_service.get_metrics_recorder", return_value=recorder),
        patch(
            "syntara.workflows.services.execution_service.resolve_user_display_name",
            new_callable=AsyncMock,
            return_value="Workflow Author",
        ),
        patch.object(service, "_to_read", new_callable=AsyncMock, return_value=Mock()),
        patch("syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch") as dispatch,
    ):
        await service.create_test_execution(
            workflow.id,
            target_node_id="target",
            pre_resolved_nodes={},
            trigger_inputs={"name": "Ada"},
            trigger_node_id="form",
        )

    session.commit.assert_awaited_once()
    dispatch.assert_not_called()
    assert list(recorder.query(metric_types={MetricType.FORM_TRIGGER_SUBMISSION_START})) == []
