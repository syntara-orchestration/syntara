"""Unit tests for form-trigger submission audit events."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.core.models.principal import PrincipalType
from syntara.workflows.audit.form_trigger import FormTriggerSubmittedEvent, FormTriggerSubmittedHandler


@pytest.mark.parametrize(
    ("principal_type", "expected_actor_type"),
    [
        (PrincipalType.USER, PrincipalType.USER),
        (PrincipalType.SERVICE_ACCOUNT, PrincipalType.SERVICE_ACCOUNT),
    ],
)
def test_submitted_handler_maps_actor_and_metadata(
    principal_type: PrincipalType,
    expected_actor_type: PrincipalType,
) -> None:
    event = FormTriggerSubmittedEvent(
        workflow_id=uuid4(),
        workflow_name="approval-workflow",
        execution_id=uuid4(),
        trigger_node_id="request-form",
        submitted_by=uuid4(),
        submitted_at=datetime.now(UTC),
        field_count=2,
        field_types=["number", "text"],
        principal_type=principal_type,
    )

    result = FormTriggerSubmittedHandler().handle(event)

    assert issubclass(FormTriggerSubmittedHandler, AuditEventHandler)
    assert (
        result.event_category,
        result.event_severity,
        result.event_status,
        result.event_action,
        result.source_component,
    ) == (
        EventCategory.WORKFLOW_EVENT,
        EventSeverity.INFO,
        EventStatus.SUCCESS,
        "form_trigger_submitted",
        "syntara.workflows",
    )
    assert result.actor_id == event.submitted_by
    assert result.actor_type == expected_actor_type
    assert result.workflow_id == event.workflow_id
    assert result.execution_id == event.execution_id
    assert result.activity_id == event.trigger_node_id
    assert result.resource_urn == f"urn:syntara:workflow:{event.workflow_id}"
    assert result.resource_name == event.workflow_name
    assert result.structured_data.model_dump() == {
        "data_type": "form-trigger-submitted",
        "error_type": None,
        "error_message": None,
        "submitted_at": event.submitted_at,
        "field_count": 2,
        "field_types": ["number", "text"],
    }


def test_submitted_audit_event_never_contains_field_labels_or_values() -> None:
    label = "CONFIDENTIAL_APPROVAL_REASON"
    value = "CONFIDENTIAL_VALUE_DO_NOT_LOG"
    event = FormTriggerSubmittedEvent(
        workflow_id=uuid4(),
        workflow_name="approval-workflow",
        execution_id=uuid4(),
        trigger_node_id="request-form",
        submitted_by=uuid4(),
        submitted_at=datetime.now(UTC),
        field_count=1,
        field_types=["text"],
    )

    result = FormTriggerSubmittedHandler().handle(event)
    serialized = result.model_dump_json()

    assert label not in serialized
    assert value not in serialized
