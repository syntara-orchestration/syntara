"""Unit tests for policy lifecycle domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.authz.audit.policy_lifecycle import (
    PolicyLifecycleEvent,
    PolicyLifecycleHandler,
)


class TestPolicyLifecycleEvent:
    """Tests for PolicyLifecycleEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        policy_id = uuid4()
        event = PolicyLifecycleEvent(
            policy_id=policy_id,
            policy_name="read-only",
            action="created",
        )
        assert event.policy_id == policy_id
        assert event.policy_name == "read-only"
        assert event.action == "created"
        assert event.project_id is None
        assert event.affected_roles_count == 0
        assert event.error_type is None


class TestPolicyLifecycleHandler:
    """Tests for PolicyLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(PolicyLifecycleHandler, AuditEventHandler)

    def test_policy_created(self) -> None:
        """Created action -> SECURITY_EVENT, INFO, SUCCESS."""
        policy_id = uuid4()
        project_id = uuid4()
        event = PolicyLifecycleEvent(
            policy_id=policy_id,
            policy_name="custom-policy",
            action="created",
            project_id=project_id,
        )
        handler = PolicyLifecycleHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "policy_created"
        assert result.event_message == "Policy created: custom-policy"
        assert result.source_component == "syntara.authz"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "policy-lifecycle"
        assert result.structured_data.action == "created"
        assert result.structured_data.policy_name == "custom-policy"

    def test_policy_updated(self) -> None:
        """Updated action -> SECURITY_EVENT, INFO, SUCCESS."""
        policy_id = uuid4()
        event = PolicyLifecycleEvent(
            policy_id=policy_id,
            policy_name="read-write",
            action="updated",
        )
        result = PolicyLifecycleHandler().handle(event)

        assert result.event_action == "policy_updated"
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS

    def test_policy_deleted_no_roles(self) -> None:
        """Deleted with no role refs -> INFO severity."""
        event = PolicyLifecycleEvent(
            policy_id=uuid4(),
            policy_name="unused-policy",
            action="deleted",
            affected_roles_count=0,
        )
        result = PolicyLifecycleHandler().handle(event)

        assert result.event_action == "policy_deleted"
        assert result.event_severity == EventSeverity.INFO
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.action == "deleted"

    def test_policy_deleted_with_roles_warning(self) -> None:
        """Deleted with role refs -> WARNING severity."""
        event = PolicyLifecycleEvent(
            policy_id=uuid4(),
            policy_name="active-policy",
            action="deleted",
            affected_roles_count=3,
        )
        result = PolicyLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.affected_roles_count == 3

    def test_resource_urn_format(self) -> None:
        """resource_urn follows RFC 8141 format."""
        policy_id = uuid4()
        event = PolicyLifecycleEvent(
            policy_id=policy_id,
            policy_name="test",
            action="created",
        )
        result = PolicyLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:policy:{policy_id}"

    def test_resource_name_from_policy_name(self) -> None:
        """resource_name is set from policy_name field."""
        policy_id = uuid4()
        event = PolicyLifecycleEvent(
            policy_id=policy_id,
            policy_name="admin-policy",
            action="created",
        )
        result = PolicyLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:policy:{policy_id}"
        assert result.resource_name == "admin-policy"

    def test_error_type_escalates_severity(self) -> None:
        """error_type set -> ERROR severity and ERROR status."""
        event = PolicyLifecycleEvent(
            policy_id=uuid4(),
            policy_name="bad-policy",
            action="created",
            error_type="DatabaseError",
        )
        result = PolicyLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "DatabaseError"
