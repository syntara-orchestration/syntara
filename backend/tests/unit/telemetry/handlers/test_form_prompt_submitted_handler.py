"""Tests for Segment telemetry emitted from prompt response events."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from syntara.forms.audit.form_prompt import FormPromptSubmittedEvent as FormPromptDomainEvent
from syntara.telemetry.events.form_prompt import FormPromptSubmittedEvent as FormPromptTelemetryEvent
from syntara.telemetry.handlers.form_prompt_submitted import FormPromptSubmittedTelemetryHandler


def _event() -> FormPromptDomainEvent:
    return FormPromptDomainEvent(
        prompt_id=uuid4(),
        workflow_id=uuid4(),
        execution_id=uuid4(),
        prompt_node_id="collect_input",
        submitted_by=uuid4(),
        submitted_at=datetime.now(UTC),
        wait_time_ms=1200,
        field_count=2,
    )


def test_response_event_emits_existing_segment_event() -> None:
    registry = Mock()
    registry.is_initialized.return_value = True
    registry.entitlement_id = "entitlement-1"

    with patch(
        "syntara.telemetry.handlers.form_prompt_submitted.get_telemetry_registry",
        return_value=registry,
    ):
        result = FormPromptSubmittedTelemetryHandler().handle(_event())

    assert result is None
    registry.send_event.assert_called_once()
    telemetry_event = registry.send_event.call_args.args[0]
    assert isinstance(telemetry_event, FormPromptTelemetryEvent)
    assert telemetry_event.to_segment_event()["event"] == "form_prompt_submitted"
    assert telemetry_event.prompt_node_id == "collect_input"
    assert telemetry_event.wait_time_ms == 1200
    assert telemetry_event.field_count == 2
    assert telemetry_event.outcome == "submitted"
    assert telemetry_event.entitlement_id == "entitlement-1"


def test_response_event_skips_segment_when_registry_is_not_initialized() -> None:
    registry = Mock()
    registry.is_initialized.return_value = False

    with patch(
        "syntara.telemetry.handlers.form_prompt_submitted.get_telemetry_registry",
        return_value=registry,
    ):
        result = FormPromptSubmittedTelemetryHandler().handle(_event())

    assert result is None
    registry.send_event.assert_not_called()
