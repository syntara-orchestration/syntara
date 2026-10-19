"""Subscription lifecycle audit maps to a sanitized AuditEvent."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventSeverity, EventStatus
from syntara.eventstreams.audit.subscription_lifecycle import (
    EventSubscriptionLifecycleEvent,
    EventSubscriptionLifecycleHandler,
)


def test_success_event_maps_counts_and_urn() -> None:
    workflow_id = uuid4()
    event = EventSubscriptionLifecycleEvent(
        workflow_id=workflow_id,
        action="published",
        created_count=1,
        updated_count=2,
        retired_count=3,
        disabled_count=0,
    )

    audit_event = EventSubscriptionLifecycleHandler().handle(event)

    assert audit_event.event_severity == EventSeverity.INFO
    assert audit_event.event_status == EventStatus.SUCCESS
    assert audit_event.event_action == "event_subscriptions_synced"
    assert audit_event.resource_urn == f"urn:syntara:workflow:{workflow_id}"
    assert audit_event.workflow_id == workflow_id
    data = audit_event.structured_data.model_dump()
    assert data["action"] == "published"
    assert data["created_count"] == 1
    assert data["retired_count"] == 3


def test_error_event_escalates_severity_without_leaking_detail() -> None:
    event = EventSubscriptionLifecycleEvent(
        workflow_id=uuid4(),
        action="published",
        error_type="IntegrityError",
    )

    audit_event = EventSubscriptionLifecycleHandler().handle(event)

    assert audit_event.event_severity == EventSeverity.ERROR
    assert audit_event.event_status == EventStatus.ERROR
    assert audit_event.structured_data.error_type == "IntegrityError"
    # Sanitized: no payloads, topics, credentials or group ids in the audit record.
    assert "topic" not in audit_event.structured_data.model_dump()
    assert "group_id" not in audit_event.structured_data.model_dump()
