"""Unit tests for credential domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.credentials.audit.credential import (
    CredentialEncryptionFailureEvent,
    CredentialEncryptionFailureHandler,
    CredentialLifecycleEvent,
    CredentialLifecycleHandler,
)


class TestCredentialLifecycleEvent:
    """Tests for CredentialLifecycleEvent dataclass."""

    def test_minimal_construction_defaults(self) -> None:
        cred_id = uuid4()
        type_id = uuid4()
        event = CredentialLifecycleEvent(
            credential_id=cred_id,
            credential_name="my-cred",
            credential_type_id=type_id,
            action="created",
        )
        assert event.credential_id == cred_id
        assert event.credential_name == "my-cred"
        assert event.action == "created"
        assert event.project_id is None
        assert event.affected_workflow_count == 0
        assert event.affected_integration_count == 0
        assert event.enabled_changed is False
        assert event.error_type is None


class TestCredentialLifecycleHandler:
    """Tests for CredentialLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(CredentialLifecycleHandler, AuditEventHandler)

    def test_credential_created(self) -> None:
        """Created action -> USER_ACTION, INFO, SUCCESS."""
        cred_id = uuid4()
        type_id = uuid4()
        project_id = uuid4()
        event = CredentialLifecycleEvent(
            credential_id=cred_id,
            credential_name="aws-key",
            credential_type_id=type_id,
            action="created",
            project_id=project_id,
        )
        handler = CredentialLifecycleHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "credential_created"
        assert result.source_component == "syntara.credentials"
        assert result.resource_urn == f"urn:syntara:credential:{cred_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "credential-lifecycle"
        assert result.structured_data.action == "created"
        assert result.structured_data.credential_name == "aws-key"
        assert result.structured_data.credential_type_id == str(type_id)

    def test_credential_updated(self) -> None:
        """Updated action -> USER_ACTION, INFO, SUCCESS."""
        cred_id = uuid4()
        event = CredentialLifecycleEvent(
            credential_id=cred_id,
            credential_name="my-cred",
            credential_type_id=uuid4(),
            action="updated",
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_action == "credential_updated"
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS

    def test_credential_deleted_no_workflows(self) -> None:
        """Deleted with no workflow refs -> INFO severity."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="unused-cred",
            credential_type_id=uuid4(),
            action="deleted",
            affected_workflow_count=0,
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_action == "credential_deleted"
        assert result.event_severity == EventSeverity.INFO
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.action == "deleted"

    def test_credential_deleted_with_workflows_warning(self) -> None:
        """Deleted with workflow refs -> WARNING severity."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="active-cred",
            credential_type_id=uuid4(),
            action="deleted",
            affected_workflow_count=3,
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.affected_workflow_count == 3

    def test_credential_deleted_with_integrations_warning(self) -> None:
        """Deleted with integration refs -> WARNING severity."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="integration-cred",
            credential_type_id=uuid4(),
            action="deleted",
            affected_integration_count=2,
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.affected_integration_count == 2

    def test_credential_deleted_with_workflows_and_integrations(self) -> None:
        """Deleted with both workflow and integration refs -> WARNING, both counts in data."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="shared-cred",
            credential_type_id=uuid4(),
            action="deleted",
            affected_workflow_count=3,
            affected_integration_count=2,
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.affected_workflow_count == 3
        assert result.structured_data.affected_integration_count == 2

    def test_credential_updated_enabled_changed_warning(self) -> None:
        """Updated with enabled_changed -> WARNING severity."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="toggled-cred",
            credential_type_id=uuid4(),
            action="updated",
            enabled_changed=True,
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.enabled_changed is True

    def test_both_enabled_changed_and_workflow_count(self) -> None:
        """Both flags set -> WARNING severity, both fields in structured_data."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="complex-update",
            credential_type_id=uuid4(),
            action="updated",
            enabled_changed=True,
            affected_workflow_count=5,
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.WARNING
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.enabled_changed is True
        assert result.structured_data.affected_workflow_count == 5

    def test_resource_urn_format(self) -> None:
        """resource_urn follows RFC 8141 format."""
        cred_id = uuid4()
        event = CredentialLifecycleEvent(
            credential_id=cred_id,
            credential_name="test",
            credential_type_id=uuid4(),
            action="created",
        )
        result = CredentialLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:credential:{cred_id}"

    def test_resource_name_from_credential_name(self) -> None:
        """resource_name is set from credential_name field."""
        cred_id = uuid4()
        event = CredentialLifecycleEvent(
            credential_id=cred_id,
            credential_name="aws-prod-creds",
            credential_type_id=uuid4(),
            action="created",
        )
        result = CredentialLifecycleHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:credential:{cred_id}"
        assert result.resource_name == "aws-prod-creds"

    def test_error_type_escalates_severity(self) -> None:
        """error_type set -> ERROR severity and ERROR status."""
        event = CredentialLifecycleEvent(
            credential_id=uuid4(),
            credential_name="bad-cred",
            credential_type_id=uuid4(),
            action="created",
            error_type="DatabaseError",
        )
        result = CredentialLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.error_type == "DatabaseError"


class TestCredentialEncryptionFailureEvent:
    """Tests for CredentialEncryptionFailureEvent dataclass."""

    def test_construction(self) -> None:
        cred_id = uuid4()
        event = CredentialEncryptionFailureEvent(
            credential_id=cred_id,
            credential_name="broken-cred",
            operation="decrypt",
            error_type="CredentialDecryptionError",
        )
        assert event.credential_id == cred_id
        assert event.operation == "decrypt"
        assert event.error_type == "CredentialDecryptionError"


class TestCredentialEncryptionFailureHandler:
    """Tests for CredentialEncryptionFailureHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(CredentialEncryptionFailureHandler, AuditEventHandler)

    def test_decrypt_failure(self) -> None:
        """Decrypt failure -> SECURITY_EVENT, ERROR, ERROR status."""
        cred_id = uuid4()
        event = CredentialEncryptionFailureEvent(
            credential_id=cred_id,
            credential_name="broken-cred",
            operation="decrypt",
            error_type="CredentialDecryptionError",
        )
        handler = CredentialEncryptionFailureHandler()
        result = handler.handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "credential_encryption_failure"
        assert result.source_component == "syntara.credentials"
        assert result.resource_urn == f"urn:syntara:credential:{cred_id}"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "credential-encryption-failure"
        assert result.structured_data.operation == "decrypt"
        assert result.structured_data.credential_name == "broken-cred"
        assert result.structured_data.error_type == "CredentialDecryptionError"

    def test_resource_name_from_credential_name(self) -> None:
        """resource_name is set from credential_name field."""
        cred_id = uuid4()
        event = CredentialEncryptionFailureEvent(
            credential_id=cred_id,
            credential_name="db-backup-creds",
            operation="decrypt",
            error_type="CryptographyError",
        )
        result = CredentialEncryptionFailureHandler().handle(event)
        assert result.resource_urn == f"urn:syntara:credential:{cred_id}"
        assert result.resource_name == "db-backup-creds"
