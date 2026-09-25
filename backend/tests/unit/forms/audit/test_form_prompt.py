"""Unit tests for form prompt lifecycle audit events and handlers."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.core.models.principal import PrincipalType
from syntara.forms.audit.form_prompt import (
    FormPromptCreatedEvent,
    FormPromptCreatedHandler,
    FormPromptExpiredEvent,
    FormPromptExpiredHandler,
    FormPromptSubmittedEvent,
    FormPromptSubmittedHandler,
)

PromptLifecycleEvent = FormPromptCreatedEvent | FormPromptSubmittedEvent | FormPromptExpiredEvent


def _assert_audit_envelope(
    result: AuditEvent,
    event: PromptLifecycleEvent,
    *,
    action: str,
    severity: EventSeverity,
) -> None:
    """Check the common workflow/resource fields shared by prompt audit handlers."""
    assert (
        result.event_category,
        result.event_severity,
        result.event_status,
        result.event_action,
        result.source_component,
    ) == (EventCategory.WORKFLOW_EVENT, severity, EventStatus.SUCCESS, action, "syntara.forms")
    assert (
        result.workflow_id,
        result.execution_id,
        result.activity_id,
        result.resource_urn,
        result.resource_name,
    ) == (
        event.workflow_id,
        event.execution_id,
        event.prompt_node_id,
        f"urn:syntara:form_prompt:{event.prompt_id}",
        event.prompt_node_id,
    )


def test_handlers_follow_the_audit_handler_contract() -> None:
    handlers = (FormPromptCreatedHandler, FormPromptSubmittedHandler, FormPromptExpiredHandler)

    assert all(issubclass(handler, AuditEventHandler) for handler in handlers)


def test_created_handler_maps_initiator_and_creation_time() -> None:
    event = FormPromptCreatedEvent(
        prompt_id=uuid4(),
        workflow_id=uuid4(),
        execution_id=uuid4(),
        prompt_node_id="collect_input",
        initiated_by=uuid4(),
        created_at=datetime.now(UTC),
    )

    result = FormPromptCreatedHandler().handle(event)
    _assert_audit_envelope(result, event, action="form_prompt_created", severity=EventSeverity.INFO)

    data = result.structured_data.model_dump()
    assert (result.actor_id, result.actor_type) == (None, PrincipalType.SYSTEM)
    assert (data["data_type"], data["initiated_by"], data["created_at"]) == (
        "form-prompt-created",
        event.initiated_by,
        event.created_at,
    )


def test_submitted_handler_maps_responder_and_omits_response_values() -> None:
    event = FormPromptSubmittedEvent(
        prompt_id=uuid4(),
        workflow_id=uuid4(),
        execution_id=uuid4(),
        prompt_node_id="collect_input",
        submitted_by=uuid4(),
        submitted_at=datetime.now(UTC),
        wait_time_ms=2500,
        field_count=2,
        principal_type=PrincipalType.USER,
    )

    result = FormPromptSubmittedHandler().handle(event)
    _assert_audit_envelope(result, event, action="form_prompt_submitted", severity=EventSeverity.INFO)

    data = result.structured_data.model_dump()
    assert (result.actor_id, result.actor_type) == (event.submitted_by, PrincipalType.USER)
    assert (data["data_type"], data["submitted_at"], data["outcome"], data["wait_time_ms"], data["field_count"]) == (
        "form-prompt-submitted",
        event.submitted_at,
        "submitted",
        2500,
        2,
    )
    assert "sensitive form value" not in result.model_dump_json()


def test_expired_handler_maps_system_actor_and_timeout_metadata() -> None:
    expired_at = datetime.now(UTC)
    event = FormPromptExpiredEvent(
        prompt_id=uuid4(),
        workflow_id=uuid4(),
        execution_id=uuid4(),
        prompt_node_id="collect_input",
        initiated_by=uuid4(),
        expired_at=expired_at,
        timeout_at=expired_at - timedelta(seconds=1),
    )

    result = FormPromptExpiredHandler().handle(event)
    _assert_audit_envelope(result, event, action="form_prompt_expired", severity=EventSeverity.WARNING)

    data = result.structured_data.model_dump()
    assert (result.actor_id, result.actor_type) == (None, PrincipalType.SYSTEM)
    assert (data["data_type"], data["initiated_by"], data["expired_at"], data["timeout_at"]) == (
        "form-prompt-expired",
        event.initiated_by,
        event.expired_at,
        event.timeout_at,
    )
