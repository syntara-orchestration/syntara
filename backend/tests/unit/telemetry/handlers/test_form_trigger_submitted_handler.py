"""Tests for Segment telemetry emitted from form-trigger submission events."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from syntara.telemetry.events.form_trigger import FormTriggerSubmittedEvent as FormTriggerTelemetryEvent
from syntara.telemetry.handlers.form_trigger_submitted import FormTriggerSubmittedTelemetryHandler
from syntara.workflows.audit.form_trigger import FormTriggerSubmittedEvent


def _event() -> FormTriggerSubmittedEvent:
    return FormTriggerSubmittedEvent(
        workflow_id=uuid4(),
        workflow_name="approval-workflow",
        execution_id=uuid4(),
        trigger_node_id="request-form",
        submitted_by=uuid4(),
        submitted_at=datetime.now(UTC),
        field_count=2,
        field_types=["number", "text"],
    )


def test_submission_emits_metadata_only_segment_event() -> None:
    registry = Mock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "entitlement-1"
    event = _event()
    field_label = "CONFIDENTIAL_APPROVAL_REASON"
    submitted_value = "CONFIDENTIAL_VALUE_DO_NOT_LOG"

    with patch(
        "syntara.telemetry.handlers.form_trigger_submitted.get_telemetry_registry",
        return_value=registry,
    ):
        result = FormTriggerSubmittedTelemetryHandler().handle(event)

    assert result is None
    registry.send_event.assert_called_once()
    telemetry_event = registry.send_event.call_args.args[0]
    assert isinstance(telemetry_event, FormTriggerTelemetryEvent)
    segment_event = telemetry_event.to_segment_event()
    properties = segment_event["properties"]
    assert isinstance(properties, dict)
    assert segment_event["event"] == "form_trigger_submitted"
    assert telemetry_event.workflow_execution_id == str(event.execution_id)
    assert telemetry_event.trigger_node_id == event.trigger_node_id
    assert telemetry_event.field_count == 2
    assert telemetry_event.field_types == ["number", "text"]
    assert telemetry_event.entitlement_id == "entitlement-1"
    assert "dynamic_dropdown" not in properties
    for key in ("input_data", "response_data", "submitted_by", "user_id", "username", "email"):
        assert key not in properties
    serialized = str(properties)
    assert field_label not in serialized
    assert submitted_value not in serialized


def test_submission_skips_segment_when_registry_is_not_initialized() -> None:
    registry = Mock()
    registry.is_initialized.return_value = False

    with patch(
        "syntara.telemetry.handlers.form_trigger_submitted.get_telemetry_registry",
        return_value=registry,
    ):
        result = FormTriggerSubmittedTelemetryHandler().handle(_event())

    assert result is None
    registry.send_event.assert_not_called()


def test_submission_swallows_segment_errors() -> None:
    registry = Mock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "entitlement-1"
    registry.send_event.side_effect = RuntimeError("Segment unavailable")

    with patch(
        "syntara.telemetry.handlers.form_trigger_submitted.get_telemetry_registry",
        return_value=registry,
    ):
        result = FormTriggerSubmittedTelemetryHandler().handle(_event())

    assert result is None
    registry.send_event.assert_called_once()
