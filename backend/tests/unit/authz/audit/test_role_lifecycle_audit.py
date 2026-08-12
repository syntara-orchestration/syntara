"""Unit tests for role lifecycle domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.authz.audit.role_lifecycle import (
    RoleLifecycleEvent,
    RoleLifecycleHandler,
)


class TestRoleLifecycleEvent:
    """Tests for RoleLifecycleEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        role_id = uuid4()
        event = RoleLifecycleEvent(
            role_id=role_id,
            role_name="Editor",
            action="created",
        )
        assert event.role_id == role_id
        assert event.role_name == "Editor"
        assert event.action == "created"
        assert event.project_id is None
        assert event.affected_assignments_count == 0
        assert event.error_type is None


class TestRoleLifecycleHandler:
    """Tests for RoleLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(RoleLifecycleHandler, AuditEventHandler)

    def test_role_created(self) -> None:
        """Created action -> SECURITY_EVENT, INFO, SUCCESS."""
        role_id = uuid4()
        project_id = uuid4()
        event = RoleLifecycleEvent(
            role_id=role_id,
            role_name="CustomRole",
            action="created",
            project_id=project_id,
        )
        handler = RoleLifecycleHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "role_created"
        assert result.event_message == "Role created: CustomRole"
        assert result.source_component == "syntara.authz"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "role-lifecycle"
        assert result.structured_data.action == "created"
        assert result.structured_data.role_name == "CustomRole"

    def test_role_updated(self) -> None:
        """Updated action -> SECURITY_EVENT, INFO, SUCCESS."""
        role_id = uuid4()
        event = RoleLifecycleEvent(
            role_id=role_id,
            role_name="Editor",
            action="updated",
        )
        result = RoleLifecycleHandler().handle(event)

        assert result.event_action == "role_updated"
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS

    def test_role_deleted_no_assignments(self) -> None:
        """Deleted with no assignments -> INFO severity."""
        event = RoleLifecycleEvent(
            role_id=uuid4(),
            role_name="unused-role",
            action="deleted",
            affected_assignments_count=0,
        )
        result = RoleLifecycleHandler().handle(event)

        assert result.event_action == "role_deleted"
        assert result.event_severity == EventSeverity.INFO
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.action == "deleted"

    def test_role_deleted_with_assignments_warning(self) -> None:
        """Deleted with assignment refs -> WARNING severity."""
        event = RoleLifecycleEvent(
            role_id=uuid4(),
            role_name="active-role",
            action="deleted",
            affected_assignments_count=3,
        )
        result = RoleLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.affected_assignments_count == 3

    def test_resource_urn_format(self) -> None:
        """resource_urn follows RFC 8141 format."""
        role_id = uuid4()
        event = RoleLifecycleEvent(
            role_id=role_id,
            role_name="test",
            action="created",
        )
        result = RoleLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:role:{role_id}"

    def test_resource_name_from_role_name(self) -> None:
        """resource_name is set from role_name field."""
        role_id = uuid4()
        event = RoleLifecycleEvent(
            role_id=role_id,
            role_name="Viewer",
            action="created",
        )
        result = RoleLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:role:{role_id}"
        assert result.resource_name == "Viewer"

    def test_error_type_escalates_severity(self) -> None:
        """error_type set -> ERROR severity and ERROR status."""
        event = RoleLifecycleEvent(
            role_id=uuid4(),
            role_name="bad-role",
            action="created",
            error_type="DatabaseError",
        )
        result = RoleLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "DatabaseError"
