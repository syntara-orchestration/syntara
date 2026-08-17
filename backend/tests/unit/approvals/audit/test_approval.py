"""Unit tests for approval audit events and handlers."""

from datetime import UTC, datetime
from uuid import uuid4

from syntara.approvals.audit.approval import (
    ApprovalDecidedEvent,
    ApprovalDecidedHandler,
    ApprovalDecisionDeniedEvent,
    ApprovalDecisionDeniedHandler,
    ApprovalRequestedEvent,
    ApprovalRequestedHandler,
)
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.core.models.principal import PrincipalType


class TestApprovalRequestedHandler:
    """Tests for ApprovalRequestedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(ApprovalRequestedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        approval_id = uuid4()
        execution_id = uuid4()
        event = ApprovalRequestedEvent(
            approval_id=approval_id,
            execution_id=execution_id,
            approval_node_id="approve_deployment",
            name="Deploy to Production",
        )
        handler = ApprovalRequestedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "approval_requested"
        assert result.source_component == "syntara.approvals"
        assert "Deploy to Production" in result.event_message
        assert result.execution_id == execution_id
        assert result.activity_id == "approve_deployment"

    def test_resource_fields(self) -> None:
        approval_id = uuid4()
        event = ApprovalRequestedEvent(
            approval_id=approval_id,
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            name="Deploy to Production",
        )
        handler = ApprovalRequestedHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:approval:{approval_id}"
        assert result.resource_name == "approve_deployment"

    def test_structured_data(self) -> None:
        event = ApprovalRequestedEvent(
            approval_id=uuid4(),
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            name="Deploy to Production",
        )
        handler = ApprovalRequestedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "approval-requested"
        assert result.structured_data.name == "Deploy to Production"  # type: ignore[attr-defined]


class TestApprovalDecisionDeniedHandler:
    """Tests for ApprovalDecisionDeniedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(ApprovalDecisionDeniedHandler, AuditEventHandler)

    def test_maps_event_to_security_event(self) -> None:
        approval_id = uuid4()
        execution_id = uuid4()
        user_id = uuid4()
        event = ApprovalDecisionDeniedEvent(
            approval_id=approval_id,
            execution_id=execution_id,
            approval_node_id="approve_deployment",
            user_id=user_id,
            username="unauthorized_user",
            action="decide",
        )
        handler = ApprovalDecisionDeniedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "authorization_denied"
        assert result.source_component == "syntara.approvals"
        assert "authorization denied" in result.event_message.lower()
        assert result.execution_id == execution_id
        assert result.activity_id == "approve_deployment"
        assert result.actor_id == user_id
        assert result.actor_username == "unauthorized_user"
        assert result.actor_type == PrincipalType.USER

    def test_resource_fields(self) -> None:
        approval_id = uuid4()
        event = ApprovalDecisionDeniedEvent(
            approval_id=approval_id,
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            user_id=uuid4(),
            username="test_user",
        )
        handler = ApprovalDecisionDeniedHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:approval:{approval_id}"
        assert result.resource_name == "approve_deployment"

    def test_structured_data(self) -> None:
        event = ApprovalDecisionDeniedEvent(
            approval_id=uuid4(),
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            user_id=uuid4(),
            username="test_user",
            action="decide",
        )
        handler = ApprovalDecisionDeniedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "authorization-denied"
        assert result.structured_data.resource_type == "approval"  # type: ignore[attr-defined]
        assert result.structured_data.action == "decide"  # type: ignore[attr-defined]

    def test_delete_action(self) -> None:
        event = ApprovalDecisionDeniedEvent(
            approval_id=uuid4(),
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            user_id=uuid4(),
            username="test_user",
            action="delete",
        )
        handler = ApprovalDecisionDeniedHandler()
        result = handler.handle(event)

        assert result.event_action == "authorization_denied"
        assert result.structured_data is not None
        assert result.structured_data.action == "delete"  # type: ignore[attr-defined]


class TestApprovalDecidedHandler:
    """Tests for ApprovalDecidedHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(ApprovalDecidedHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        approval_id = uuid4()
        execution_id = uuid4()
        decided_by = uuid4()
        decided_at = datetime.now(UTC)
        event = ApprovalDecidedEvent(
            approval_id=approval_id,
            execution_id=execution_id,
            approval_node_id="approve_deployment",
            decision="approved",
            decided_by=decided_by,
            decided_at=decided_at,
            wait_time_ms=5000,
        )
        handler = ApprovalDecidedHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "approval_decided"
        assert result.source_component == "syntara.approvals"
        assert "approved" in result.event_message
        assert result.execution_id == execution_id
        assert result.activity_id == "approve_deployment"
        assert result.actor_id == decided_by
        assert result.actor_type == PrincipalType.USER

    def test_resource_fields(self) -> None:
        approval_id = uuid4()
        event = ApprovalDecidedEvent(
            approval_id=approval_id,
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            decision="approved",
            decided_by=uuid4(),
            decided_at=datetime.now(UTC),
            wait_time_ms=5000,
        )
        handler = ApprovalDecidedHandler()
        result = handler.handle(event)

        assert result.resource_urn == f"urn:syntara:approval:{approval_id}"
        assert result.resource_name == "approve_deployment"

    def test_structured_data(self) -> None:
        event = ApprovalDecidedEvent(
            approval_id=uuid4(),
            execution_id=uuid4(),
            approval_node_id="approve_deployment",
            decision="rejected",
            decided_by=uuid4(),
            decided_at=datetime.now(UTC),
            wait_time_ms=3000,
        )
        handler = ApprovalDecidedHandler()
        result = handler.handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "approval-decided"
        assert result.structured_data.decision == "rejected"  # type: ignore[attr-defined]
        assert result.structured_data.wait_time_ms == 3000  # type: ignore[attr-defined]
