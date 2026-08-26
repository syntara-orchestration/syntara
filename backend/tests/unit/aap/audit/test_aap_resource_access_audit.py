"""Unit tests for AAP domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.aap.audit.aap_resource_access import (
    AAPAccessAction,
    AAPResourceAccessEvent,
    AAPResourceAccessHandler,
    AAPResourceType,
)
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType


class TestAAPResourceAccessEvent:
    """Tests for AAPResourceAccessEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.ORGANIZATIONS,
            action=AAPAccessAction.LIST,
        )
        assert event.resource_type == AAPResourceType.ORGANIZATIONS
        assert event.action == AAPAccessAction.LIST
        assert event.user_id is None
        assert event.username is None
        assert event.result_count is None
        assert event.resource_id is None
        assert event.credential_used is False
        assert event.search_filter is None
        assert event.organization_filter is None
        assert event.error_type is None

    def test_full_construction(self) -> None:
        user_id = uuid4()
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.JOB_TEMPLATES,
            action=AAPAccessAction.LIST,
            user_id=user_id,
            username="admin",
            result_count=25,
            credential_used=True,
            search_filter="deploy",
            organization_filter="Engineering",
        )
        assert event.user_id == user_id
        assert event.username == "admin"
        assert event.result_count == 25
        assert event.credential_used is True
        assert event.search_filter == "deploy"
        assert event.organization_filter == "Engineering"


class TestAAPResourceAccessHandler:
    """Tests for AAPResourceAccessHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(AAPResourceAccessHandler, AuditEventHandler)

    def test_list_organizations_success(self) -> None:
        """List action -> USER_ACTION, INFO, SUCCESS with count in message."""
        user_id = uuid4()
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.ORGANIZATIONS,
            action=AAPAccessAction.LIST,
            user_id=user_id,
            username="testuser",
            result_count=5,
        )
        handler = AAPResourceAccessHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "aap_organizations_listed"
        assert result.source_component == "syntara.aap"
        assert result.resource_urn == "urn:syntara:aap:organizations"
        assert result.actor_id == user_id
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "testuser"
        assert result.resource_name is None
        assert "5 results" in result.event_message

    def test_get_job_template_success(self) -> None:
        """Get action -> resource_id in URN and structured_data, resource_name set."""
        user_id = uuid4()
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.JOB_TEMPLATES,
            action=AAPAccessAction.GET,
            user_id=user_id,
            username="admin",
            resource_id=42,
            resource_name="Deploy Playbook",
            credential_used=True,
        )
        result = AAPResourceAccessHandler().handle(event)

        assert result.event_action == "aap_job_templates_retrieved"
        assert result.resource_urn == "urn:syntara:aap:job_templates:42"
        assert result.resource_name == "Deploy Playbook"
        assert "42" in result.event_message
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "aap-resource-access"
        assert result.structured_data.resource_id == 42
        assert result.structured_data.credential_used is True

    def test_list_with_search_filter(self) -> None:
        """Search filter is captured in structured_data."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.INVENTORIES,
            action=AAPAccessAction.LIST,
            user_id=uuid4(),
            result_count=3,
            search_filter="production",
        )
        result = AAPResourceAccessHandler().handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.search_filter == "production"

    def test_list_with_organization_filter(self) -> None:
        """Organization filter is captured in structured_data."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.EXECUTION_ENVIRONMENTS,
            action=AAPAccessAction.LIST,
            user_id=uuid4(),
            result_count=2,
            organization_filter="Engineering",
        )
        result = AAPResourceAccessHandler().handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.organization_filter == "Engineering"

    def test_credential_used_tracking(self) -> None:
        """credential_used=True is captured in structured_data."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.CREDENTIALS,
            action=AAPAccessAction.LIST,
            user_id=uuid4(),
            result_count=10,
            credential_used=True,
        )
        result = AAPResourceAccessHandler().handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.credential_used is True

    def test_credential_not_used_tracking(self) -> None:
        """credential_used=False is captured when the event records no Orchestrator credential."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.LABELS,
            action=AAPAccessAction.LIST,
            user_id=uuid4(),
            result_count=0,
            credential_used=False,
        )
        result = AAPResourceAccessHandler().handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.credential_used is False

    def test_error_escalates_severity(self) -> None:
        """error_type set -> ERROR severity and ERROR status."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.JOB_TEMPLATES,
            action=AAPAccessAction.LIST,
            user_id=uuid4(),
            error_type="AAPConnectionError",
        )
        result = AAPResourceAccessHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert "failed" in result.event_message
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "AAPConnectionError"

    def test_list_zero_results(self) -> None:
        """List with 0 results still emits SUCCESS."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.INSTANCE_GROUPS,
            action=AAPAccessAction.LIST,
            user_id=uuid4(),
            result_count=0,
        )
        result = AAPResourceAccessHandler().handle(event)

        assert result.event_status == EventStatus.SUCCESS
        assert "0 results" in result.event_message

    def test_no_user_id_actor_type_system(self) -> None:
        """No user_id -> actor_type=SYSTEM (consistent with peer handlers)."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.ORGANIZATIONS,
            action=AAPAccessAction.LIST,
            result_count=1,
        )
        result = AAPResourceAccessHandler().handle(event)

        assert result.actor_type == PrincipalType.SYSTEM
        assert result.actor_id is None

    def test_resource_urn_format_list(self) -> None:
        """List URN follows urn:syntara:aap:{resource_type} format."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.WORKFLOW_JOB_TEMPLATES,
            action=AAPAccessAction.LIST,
            result_count=5,
        )
        result = AAPResourceAccessHandler().handle(event)
        assert result.resource_urn == "urn:syntara:aap:workflow_job_templates"

    def test_resource_urn_format_get(self) -> None:
        """Get URN follows urn:syntara:aap:{resource_type}:{id} format."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.WORKFLOW_JOB_TEMPLATES,
            action=AAPAccessAction.GET,
            resource_id=99,
        )
        result = AAPResourceAccessHandler().handle(event)
        assert result.resource_urn == "urn:syntara:aap:workflow_job_templates:99"

    def test_structured_data_type_discriminator(self) -> None:
        """data_type is always 'aap-resource-access'."""
        event = AAPResourceAccessEvent(
            resource_type=AAPResourceType.ORGANIZATIONS,
            action=AAPAccessAction.LIST,
            result_count=1,
        )
        result = AAPResourceAccessHandler().handle(event)
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "aap-resource-access"

    def test_all_resource_types_produce_valid_events(self) -> None:
        """Every AAPResourceType produces a valid AuditEvent."""
        handler = AAPResourceAccessHandler()
        for resource_type in AAPResourceType:
            event = AAPResourceAccessEvent(
                resource_type=resource_type,
                action=AAPAccessAction.LIST,
                user_id=uuid4(),
                result_count=1,
            )
            result = handler.handle(event)
            assert result.event_category == EventCategory.USER_ACTION
            assert result.event_status == EventStatus.SUCCESS
            assert resource_type.value in result.event_action
            assert result.resource_urn is not None
            assert resource_type.value in result.resource_urn
