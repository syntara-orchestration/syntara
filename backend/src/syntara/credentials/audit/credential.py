"""Credential domain events and audit handlers.

Emits audit trail events for credential lifecycle operations and encryption failures.

Requirements: AAP-73909
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

if TYPE_CHECKING:
    from uuid import UUID


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class CredentialLifecycleEvent:
    """Domain event fired when a credential is created, updated, or deleted."""

    credential_id: UUID
    credential_name: str
    credential_type_id: UUID
    action: str  # "created", "updated", "deleted"
    project_id: UUID | None = field(default=None)
    affected_workflow_count: int = field(default=0)
    affected_integration_count: int = field(default=0)
    enabled_changed: bool = field(default=False)
    error_type: str | None = field(default=None)


@dataclass
class CredentialEncryptionFailureEvent:
    """Domain event fired when credential decryption fails."""

    credential_id: UUID
    credential_name: str
    operation: str  # "decrypt"
    error_type: str


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class CredentialLifecycleHandler(AuditEventHandler[CredentialLifecycleEvent]):
    """Maps a CredentialLifecycleEvent to an AuditEvent."""

    def handle(self, event: CredentialLifecycleEvent) -> AuditEvent:
        """Map a CredentialLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        severity = EventSeverity.INFO
        if is_error:
            severity = EventSeverity.ERROR
        elif (
            event.action == "deleted" and (event.affected_workflow_count > 0 or event.affected_integration_count > 0)
        ) or event.enabled_changed:
            severity = EventSeverity.WARNING

        data = AuditContextData(
            data_type="credential-lifecycle",
            action=event.action,
            credential_name=event.credential_name,
            credential_type_id=str(event.credential_type_id),
        )
        if event.affected_workflow_count > 0:
            data.affected_workflow_count = event.affected_workflow_count
        if event.affected_integration_count > 0:
            data.affected_integration_count = event.affected_integration_count
        if event.enabled_changed:
            data.enabled_changed = event.enabled_changed
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=severity,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"credential_{event.action}",
            event_message=f"Credential {event.action}: {event.credential_name}",
            source_component="syntara.credentials",
            structured_data=data,
            resource_urn=f"urn:syntara:credential:{event.credential_id}",
            resource_name=event.credential_name,
        )


class CredentialEncryptionFailureHandler(AuditEventHandler[CredentialEncryptionFailureEvent]):
    """Maps a CredentialEncryptionFailureEvent to an AuditEvent."""

    def handle(self, event: CredentialEncryptionFailureEvent) -> AuditEvent:
        """Map a CredentialEncryptionFailureEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="credential-encryption-failure",
            operation=event.operation,
            credential_name=event.credential_name,
            error_type=event.error_type,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.ERROR,
            event_status=EventStatus.ERROR,
            event_action="credential_encryption_failure",
            event_message=f"Credential {event.operation} failed: {event.credential_name}",
            source_component="syntara.credentials",
            structured_data=data,
            resource_urn=f"urn:syntara:credential:{event.credential_id}",
            resource_name=event.credential_name,
        )
