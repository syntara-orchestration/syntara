"""Unit tests for SA rejection audit events and handlers."""

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.auth.audit.sa_rejection import (
    DisabledSACredentialRejectionEvent,
    DisabledSACredentialRejectionHandler,
    DisabledSARejectionEvent,
    DisabledSARejectionHandler,
    MissingSACredentialClaimEvent,
    MissingSACredentialClaimHandler,
    StaleSATokenDetectionEvent,
    StaleSATokenDetectionHandler,
)
from syntara.core.models.principal import PrincipalType


class TestDisabledSARejectionHandler:
    """Tests for DisabledSARejectionHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(DisabledSARejectionHandler, AuditEventHandler)

    def test_maps_disabled_sa_to_audit_event(self) -> None:
        sa_id = str(uuid4())
        event = DisabledSARejectionEvent(service_account_id=sa_id, sa_status="disabled", is_alive=True)
        result = DisabledSARejectionHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "disabled_sa_rejected"
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT
        assert result.source_component == "syntara.auth.middleware"
        assert "disabled" in result.event_message

    def test_maps_deleted_sa_to_audit_event(self) -> None:
        sa_id = str(uuid4())
        event = DisabledSARejectionEvent(service_account_id=sa_id, sa_status="active", is_alive=False)
        result = DisabledSARejectionHandler().handle(event)

        assert result.event_action == "disabled_sa_rejected"
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT

    def test_resource_fields(self) -> None:
        sa_id = str(uuid4())
        event = DisabledSARejectionEvent(service_account_id=sa_id, sa_status="disabled", is_alive=True)
        result = DisabledSARejectionHandler().handle(event)

        assert result.resource_urn == f"urn:syntara:service-account:{sa_id}"
        assert result.resource_name == sa_id

    def test_structured_data(self) -> None:
        sa_id = str(uuid4())
        event = DisabledSARejectionEvent(service_account_id=sa_id, sa_status="disabled", is_alive=True)
        result = DisabledSARejectionHandler().handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "disabled-sa-rejection"


class TestDisabledSACredentialRejectionHandler:
    """Tests for DisabledSACredentialRejectionHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(DisabledSACredentialRejectionHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        sa_id = str(uuid4())
        cred_id = str(uuid4())
        event = DisabledSACredentialRejectionEvent(
            service_account_id=sa_id, credential_id=cred_id, credential_status="disabled"
        )
        result = DisabledSACredentialRejectionHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "disabled_sa_credential_rejected"
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT
        assert result.source_component == "syntara.auth.middleware"
        assert "disabled" in result.event_message
        assert cred_id in result.event_message

    def test_resource_fields(self) -> None:
        sa_id = str(uuid4())
        cred_id = str(uuid4())
        event = DisabledSACredentialRejectionEvent(
            service_account_id=sa_id, credential_id=cred_id, credential_status="disabled"
        )
        result = DisabledSACredentialRejectionHandler().handle(event)

        assert result.resource_urn == f"urn:syntara:service-account:{sa_id}"
        assert result.resource_name == sa_id

    def test_structured_data(self) -> None:
        sa_id = str(uuid4())
        cred_id = str(uuid4())
        event = DisabledSACredentialRejectionEvent(
            service_account_id=sa_id, credential_id=cred_id, credential_status="deleted"
        )
        result = DisabledSACredentialRejectionHandler().handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "disabled-sa-credential-rejection"
        assert result.structured_data.credential_id == cred_id  # type: ignore[attr-defined]
        assert result.structured_data.credential_status == "deleted"  # type: ignore[attr-defined]


class TestMissingSACredentialClaimHandler:
    """Tests for MissingSACredentialClaimHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(MissingSACredentialClaimHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        sa_id = str(uuid4())
        event = MissingSACredentialClaimEvent(service_account_id=sa_id)
        result = MissingSACredentialClaimHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "missing_sa_credential_claim_rejected"
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT
        assert result.source_component == "syntara.auth.middleware"
        assert "cred_id" in result.event_message

    def test_resource_fields(self) -> None:
        sa_id = str(uuid4())
        event = MissingSACredentialClaimEvent(service_account_id=sa_id)
        result = MissingSACredentialClaimHandler().handle(event)

        assert result.resource_urn == f"urn:syntara:service-account:{sa_id}"
        assert result.resource_name == sa_id

    def test_structured_data(self) -> None:
        sa_id = str(uuid4())
        event = MissingSACredentialClaimEvent(service_account_id=sa_id)
        result = MissingSACredentialClaimHandler().handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "missing-sa-credential-claim"


class TestStaleSATokenDetectionHandler:
    """Tests for StaleSATokenDetectionHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(StaleSATokenDetectionHandler, AuditEventHandler)

    def test_maps_event_to_audit_event(self) -> None:
        sa_id = str(uuid4())
        event = StaleSATokenDetectionEvent(service_account_id=sa_id, token_version=2, current_version=5)
        result = StaleSATokenDetectionHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "stale_sa_token_detected"
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT
        assert result.source_component == "syntara.auth.middleware"

    def test_resource_fields(self) -> None:
        sa_id = str(uuid4())
        event = StaleSATokenDetectionEvent(service_account_id=sa_id, token_version=2, current_version=5)
        result = StaleSATokenDetectionHandler().handle(event)

        assert result.resource_urn == f"urn:syntara:service-account:{sa_id}"
        assert result.resource_name == sa_id

    def test_structured_data(self) -> None:
        sa_id = str(uuid4())
        event = StaleSATokenDetectionEvent(service_account_id=sa_id, token_version=2, current_version=5)
        result = StaleSATokenDetectionHandler().handle(event)

        assert result.structured_data is not None
        assert result.structured_data.data_type == "stale-sa-token-detection"
        assert result.structured_data.token_version == 2  # type: ignore[attr-defined]
        assert result.structured_data.current_version == 5  # type: ignore[attr-defined]
