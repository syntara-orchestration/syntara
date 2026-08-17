"""Audit events for service account token rejections in StaleTokenMiddleware."""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType

_SOURCE_COMPONENT = "syntara.auth.middleware"


@dataclass
class DisabledSARejectionEvent:
    """Emitted when a request from a disabled or deleted service account is rejected."""

    service_account_id: str
    sa_status: str
    is_alive: bool


class DisabledSARejectionHandler(AuditEventHandler[DisabledSARejectionEvent]):
    """Maps a DisabledSARejectionEvent to a normalized AuditEvent."""

    def handle(self, event: DisabledSARejectionEvent) -> AuditEvent:
        """Map a DisabledSARejectionEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="disabled-sa-rejection",
            sa_status=event.sa_status,
            is_alive=event.is_alive,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="disabled_sa_rejected",
            event_message=f"Rejected request from disabled/deleted service account ({event.sa_status})",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SERVICE_ACCOUNT,
            resource_urn=f"urn:syntara:service-account:{quote(event.service_account_id, safe='')}",
            resource_name=event.service_account_id,
        )


@dataclass
class DisabledSACredentialRejectionEvent:
    """Emitted when a request is rejected because the SA credential is disabled or deleted."""

    service_account_id: str
    credential_id: str
    credential_status: str


class DisabledSACredentialRejectionHandler(AuditEventHandler[DisabledSACredentialRejectionEvent]):
    """Maps a DisabledSACredentialRejectionEvent to a normalized AuditEvent."""

    def handle(self, event: DisabledSACredentialRejectionEvent) -> AuditEvent:
        """Map a DisabledSACredentialRejectionEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="disabled-sa-credential-rejection",
            credential_status=event.credential_status,
            credential_id=event.credential_id,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="disabled_sa_credential_rejected",
            event_message=(
                f"Rejected request: SA credential {event.credential_status} (credential {event.credential_id})"
            ),
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SERVICE_ACCOUNT,
            resource_urn=f"urn:syntara:service-account:{quote(event.service_account_id, safe='')}",
            resource_name=event.service_account_id,
        )


@dataclass
class ExpiredSACredentialRejectionEvent:
    """Emitted when a request is rejected because the SA credential has expired."""

    service_account_id: str
    credential_id: str
    expires_at: datetime


class ExpiredSACredentialRejectionHandler(AuditEventHandler[ExpiredSACredentialRejectionEvent]):
    """Maps an ExpiredSACredentialRejectionEvent to a normalized AuditEvent."""

    def handle(self, event: ExpiredSACredentialRejectionEvent) -> AuditEvent:
        """Map an ExpiredSACredentialRejectionEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="expired-sa-credential-rejection",
            credential_id=event.credential_id,
            expires_at=event.expires_at.isoformat(),
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="expired_sa_credential_rejected",
            event_message=(
                f"Rejected request: SA credential expired at {event.expires_at.isoformat()}"
                f" (credential {event.credential_id})"
            ),
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SERVICE_ACCOUNT,
            resource_urn=f"urn:syntara:service-account:{quote(event.service_account_id, safe='')}",
            resource_name=event.service_account_id,
        )


@dataclass
class MissingSACredentialClaimEvent:
    """Emitted when an SA token is rejected because it lacks the cred_id claim."""

    service_account_id: str


class MissingSACredentialClaimHandler(AuditEventHandler[MissingSACredentialClaimEvent]):
    """Maps a MissingSACredentialClaimEvent to a normalized AuditEvent."""

    def handle(self, event: MissingSACredentialClaimEvent) -> AuditEvent:
        """Map a MissingSACredentialClaimEvent to a normalized AuditEvent."""
        data = AuditContextData(data_type="missing-sa-credential-claim")

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="missing_sa_credential_claim_rejected",
            event_message="Rejected SA token missing cred_id claim",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SERVICE_ACCOUNT,
            resource_urn=f"urn:syntara:service-account:{quote(event.service_account_id, safe='')}",
            resource_name=event.service_account_id,
        )


@dataclass
class StaleSATokenDetectionEvent:
    """Emitted when a stale service account token is detected."""

    service_account_id: str
    token_version: int
    current_version: int


class StaleSATokenDetectionHandler(AuditEventHandler[StaleSATokenDetectionEvent]):
    """Maps a StaleSATokenDetectionEvent to a normalized AuditEvent."""

    def handle(self, event: StaleSATokenDetectionEvent) -> AuditEvent:
        """Map a StaleSATokenDetectionEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="stale-sa-token-detection",
            token_version=event.token_version,
            current_version=event.current_version,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="stale_sa_token_detected",
            event_message="Stale service account token detected",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            actor_type=PrincipalType.SERVICE_ACCOUNT,
            resource_urn=f"urn:syntara:service-account:{quote(event.service_account_id, safe='')}",
            resource_name=event.service_account_id,
        )
