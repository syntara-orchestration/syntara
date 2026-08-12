"""Unit tests for identity provider domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.identity_providers.audit.identity_provider import (
    IdentityProviderLifecycleEvent,
    IdentityProviderLifecycleHandler,
)


class TestIdentityProviderLifecycleEvent:
    """Tests for IdentityProviderLifecycleEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        provider_id = uuid4()
        event = IdentityProviderLifecycleEvent(
            provider_id=provider_id,
            provider_name="my-idp",
            action="created",
        )
        assert event.provider_id == provider_id
        assert event.provider_name == "my-idp"
        assert event.action == "created"
        assert event.disable_tls_verify is False
        assert event.error_type is None

    def test_construction_with_all_fields(self) -> None:
        provider_id = uuid4()
        event = IdentityProviderLifecycleEvent(
            provider_id=provider_id,
            provider_name="insecure-idp",
            action="updated",
            disable_tls_verify=True,
            error_type="SomeError",
        )
        assert event.provider_id == provider_id
        assert event.provider_name == "insecure-idp"
        assert event.action == "updated"
        assert event.disable_tls_verify is True
        assert event.error_type == "SomeError"


class TestIdentityProviderLifecycleHandler:
    """Tests for IdentityProviderLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(IdentityProviderLifecycleHandler, AuditEventHandler)

    def test_provider_created(self) -> None:
        provider_id = uuid4()
        event = IdentityProviderLifecycleEvent(
            provider_id=provider_id,
            provider_name="corp-sso",
            action="created",
        )
        result = IdentityProviderLifecycleHandler().handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "identity_provider_created"
        assert result.event_message == "Identity provider created: corp-sso"
        assert result.source_component == "syntara.identity_providers"
        assert result.resource_urn == f"urn:syntara:identity_provider:{provider_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "identity-provider-lifecycle"
        assert result.structured_data.action == "created"
        assert result.structured_data.provider_name == "corp-sso"
        assert result.structured_data.disable_tls_verify is False

    def test_provider_updated(self) -> None:
        provider_id = uuid4()
        event = IdentityProviderLifecycleEvent(
            provider_id=provider_id,
            provider_name="corp-sso",
            action="updated",
        )
        result = IdentityProviderLifecycleHandler().handle(event)

        assert result.event_action == "identity_provider_updated"
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS

    def test_disable_tls_verify_escalates_to_warning(self) -> None:
        event = IdentityProviderLifecycleEvent(
            provider_id=uuid4(),
            provider_name="insecure-idp",
            action="created",
            disable_tls_verify=True,
        )
        result = IdentityProviderLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.disable_tls_verify is True

    def test_disable_tls_verify_on_update(self) -> None:
        event = IdentityProviderLifecycleEvent(
            provider_id=uuid4(),
            provider_name="insecure-idp",
            action="updated",
            disable_tls_verify=True,
        )
        result = IdentityProviderLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert result.event_action == "identity_provider_updated"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.disable_tls_verify is True

    def test_error_type_escalates_to_error(self) -> None:
        event = IdentityProviderLifecycleEvent(
            provider_id=uuid4(),
            provider_name="bad-idp",
            action="created",
            error_type="DatabaseError",
        )
        result = IdentityProviderLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "DatabaseError"

    def test_error_takes_precedence_over_tls_warning(self) -> None:
        event = IdentityProviderLifecycleEvent(
            provider_id=uuid4(),
            provider_name="bad-insecure-idp",
            action="created",
            disable_tls_verify=True,
            error_type="IntegrityError",
        )
        result = IdentityProviderLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR

    def test_resource_urn_format(self) -> None:
        provider_id = uuid4()
        event = IdentityProviderLifecycleEvent(
            provider_id=provider_id,
            provider_name="test",
            action="created",
        )
        result = IdentityProviderLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:identity_provider:{provider_id}"

    def test_resource_name_from_provider_name(self) -> None:
        """resource_name is set from provider_name field."""
        provider_id = uuid4()
        event = IdentityProviderLifecycleEvent(
            provider_id=provider_id,
            provider_name="okta-prod",
            action="created",
        )
        result = IdentityProviderLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:identity_provider:{provider_id}"
        assert result.resource_name == "okta-prod"
