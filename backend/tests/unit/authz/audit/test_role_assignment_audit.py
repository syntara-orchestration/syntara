"""Unit tests for role assignment domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.authz.audit.role_assignment import (
    RoleAssignmentEvent,
    RoleAssignmentHandler,
)


class TestRoleAssignmentEvent:
    """Tests for RoleAssignmentEvent dataclass."""

    def test_principal_construction_defaults(self) -> None:
        assignment_id = uuid4()
        principal_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            principal_type="user",
            principal_id=principal_id,
            principal_name="admin",
            role_name="Editor",
            action="assigned",
        )
        assert event.assignment_id == assignment_id
        assert event.principal_type == "user"
        assert event.principal_id == principal_id
        assert event.principal_name == "admin"
        assert event.group_id is None
        assert event.group_name is None
        assert event.role_name == "Editor"
        assert event.action == "assigned"
        assert event.project_id is None
        assert event.error_type is None

    def test_group_construction_defaults(self) -> None:
        assignment_id = uuid4()
        group_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            group_id=group_id,
            group_name="developers",
            role_name="Viewer",
            action="assigned",
        )
        assert event.group_id == group_id
        assert event.group_name == "developers"
        assert event.principal_id is None
        assert event.principal_type is None
        assert event.principal_name is None


class TestRoleAssignmentHandler:
    """Tests for RoleAssignmentHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(RoleAssignmentHandler, AuditEventHandler)

    def test_role_assigned_to_principal(self) -> None:
        """Assigned action -> SECURITY_EVENT, INFO, SUCCESS."""
        assignment_id = uuid4()
        principal_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            principal_type="user",
            principal_id=principal_id,
            principal_name="alice",
            role_name="Admin",
            action="assigned",
        )
        handler = RoleAssignmentHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "role_assigned"
        assert result.source_component == "syntara.authz"
        assert result.event_message == "Role assigned: Admin -> user alice"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "role-assignment"
        assert result.structured_data.action == "assigned"
        assert result.structured_data.principal_type == "user"
        assert result.structured_data.principal_name == "alice"
        assert result.structured_data.role_name == "Admin"

    def test_role_assigned_to_group(self) -> None:
        """Group assignment populates group_name, not principal fields."""
        assignment_id = uuid4()
        group_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            group_id=group_id,
            group_name="developers",
            role_name="Viewer",
            action="assigned",
        )
        result = RoleAssignmentHandler().handle(event)

        assert result.event_action == "role_assigned"
        assert result.event_message == "Role assigned: Viewer -> group developers"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.group_name == "developers"
        assert not hasattr(result.structured_data, "principal_type") or result.structured_data.principal_type is None

    def test_role_revoked_from_group(self) -> None:
        """Revoked action -> event_action=role_revoked."""
        assignment_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            group_id=uuid4(),
            group_name="developers",
            role_name="Viewer",
            action="revoked",
        )
        result = RoleAssignmentHandler().handle(event)

        assert result.event_action == "role_revoked"
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_message == "Role revoked: Viewer -> group developers"

    def test_with_project_id(self) -> None:
        """Verify project_id appears in structured_data."""
        project_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=uuid4(),
            principal_type="user",
            principal_id=uuid4(),
            principal_name="bob",
            role_name="Editor",
            action="assigned",
            project_id=project_id,
        )
        result = RoleAssignmentHandler().handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.project_id == str(project_id)

    def test_resource_urn_format(self) -> None:
        """resource_urn follows RFC 8141 format."""
        assignment_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            principal_type="user",
            principal_id=uuid4(),
            principal_name="test",
            role_name="Admin",
            action="assigned",
        )
        result = RoleAssignmentHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:role-assignment:{assignment_id}"

    def test_resource_name_from_role_name(self) -> None:
        """resource_name is set from role_name field."""
        assignment_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            principal_type="user",
            principal_id=uuid4(),
            principal_name="alice",
            role_name="Editor",
            action="assigned",
        )
        result = RoleAssignmentHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:role-assignment:{assignment_id}"
        assert result.resource_name == "Editor"

    def test_orphaned_principal_uses_fallback_label(self) -> None:
        """When principal_type and principal_name are both None, label falls back to 'principal'."""
        assignment_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            role_name="Admin",
            action="revoked",
        )
        result = RoleAssignmentHandler().handle(event)

        assert result.event_message == "Role revoked: Admin -> principal"

    def test_group_without_name_uses_bare_label(self) -> None:
        """Group assignment with group_name=None uses 'group' as label."""
        assignment_id = uuid4()
        event = RoleAssignmentEvent(
            assignment_id=assignment_id,
            group_id=uuid4(),
            group_name=None,
            role_name="Viewer",
            action="revoked",
        )
        result = RoleAssignmentHandler().handle(event)

        assert result.event_message == "Role revoked: Viewer -> group"

    def test_error_type_escalates_severity(self) -> None:
        """error_type set -> ERROR severity and ERROR status."""
        event = RoleAssignmentEvent(
            assignment_id=uuid4(),
            principal_type="user",
            principal_id=uuid4(),
            principal_name="bad-user",
            role_name="Admin",
            action="assigned",
            error_type="DatabaseError",
        )
        result = RoleAssignmentHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "DatabaseError"
