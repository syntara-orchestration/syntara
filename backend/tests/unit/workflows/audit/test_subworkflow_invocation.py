"""Unit tests for Sub-workflow invocation and authorization audit records."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.workflows.audit.subworkflow_invocation import (
    SubWorkflowAuthorizationDeniedEvent,
    SubWorkflowAuthorizationDeniedHandler,
    SubWorkflowInvocationEvent,
    SubWorkflowInvocationHandler,
)


def test_successful_reference_invocation_records_correlated_identifiers() -> None:
    actor_id = uuid4()
    parent_workflow_id = uuid4()
    parent_execution_id = uuid4()
    child_workflow_id = uuid4()
    child_execution_id = uuid4()
    event = SubWorkflowInvocationEvent(
        actor_id=actor_id,
        parent_workflow_id=parent_workflow_id,
        parent_execution_id=parent_execution_id,
        parent_node_id="invoke_child",
        child_workflow_id=child_workflow_id,
        child_execution_id=child_execution_id,
    )

    audit_event = SubWorkflowInvocationHandler().handle(event)

    assert audit_event.event_category == EventCategory.WORKFLOW_EVENT
    assert audit_event.event_severity == EventSeverity.INFO
    assert audit_event.event_status == EventStatus.SUCCESS
    assert audit_event.event_action == "subworkflow_invocation"
    assert audit_event.actor_id == actor_id
    assert audit_event.workflow_id == parent_workflow_id
    assert audit_event.execution_id == parent_execution_id
    assert audit_event.resource_urn == f"urn:syntara:workflow:{child_workflow_id}"
    data = audit_event.structured_data.model_dump(exclude_none=True)
    assert data["parent_workflow_id"] == str(parent_workflow_id)
    assert data["parent_execution_id"] == str(parent_execution_id)
    assert data["parent_node_id"] == "invoke_child"
    assert data["child_workflow_id"] == str(child_workflow_id)
    assert data["child_execution_id"] == str(child_execution_id)
    assert data["mode"] == "reference"
    assert data["status"] == "success"
    assert "input_data" not in data
    assert "output_data" not in data


def test_authorization_denial_records_target_and_reason_without_child_execution() -> None:
    actor_id = uuid4()
    parent_workflow_id = uuid4()
    parent_execution_id = uuid4()
    child_workflow_id = uuid4()
    event = SubWorkflowAuthorizationDeniedEvent(
        actor_id=actor_id,
        parent_workflow_id=parent_workflow_id,
        parent_execution_id=parent_execution_id,
        parent_node_id="invoke_child",
        child_workflow_id=child_workflow_id,
        denial_reason="policy_deny",
    )

    audit_event = SubWorkflowAuthorizationDeniedHandler().handle(event)

    assert audit_event.event_category == EventCategory.SECURITY_EVENT
    assert audit_event.event_severity == EventSeverity.WARNING
    assert audit_event.event_status == EventStatus.ERROR
    assert audit_event.event_action == "subworkflow_authorization_denied"
    assert audit_event.actor_id == actor_id
    assert audit_event.workflow_id == parent_workflow_id
    assert audit_event.execution_id == parent_execution_id
    assert audit_event.resource_urn == f"urn:syntara:workflow:{child_workflow_id}"
    data = audit_event.structured_data.model_dump(exclude_none=True)
    assert data["parent_workflow_id"] == str(parent_workflow_id)
    assert data["parent_execution_id"] == str(parent_execution_id)
    assert data["child_workflow_id"] == str(child_workflow_id)
    assert data["denial_reason"] == "policy_deny"
    assert data["mode"] == "reference"
    assert data["status"] == "denied"
    assert "child_execution_id" not in data
