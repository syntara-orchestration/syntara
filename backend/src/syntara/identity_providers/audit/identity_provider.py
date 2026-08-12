"""Identity provider domain events and audit handlers.

Emits audit trail events for identity provider lifecycle operations,
including security-relevant configuration changes (e.g. TLS verification).

Requirements: AAP-74872
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


@dataclass
class IdentityProviderLifecycleEvent:
    """Domain event fired when an identity provider is created or updated."""

    provider_id: UUID
    provider_name: str
    action: str  # "created", "updated"
    disable_tls_verify: bool = field(default=False)
    error_type: str | None = field(default=None)


class IdentityProviderLifecycleHandler(AuditEventHandler[IdentityProviderLifecycleEvent]):
    """Maps an IdentityProviderLifecycleEvent to an AuditEvent."""

    def handle(self, event: IdentityProviderLifecycleEvent) -> AuditEvent:
        """Map an IdentityProviderLifecycleEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        severity = EventSeverity.INFO
        if is_error:
            severity = EventSeverity.ERROR
        elif event.disable_tls_verify:
            severity = EventSeverity.WARNING

        data = AuditContextData(
            data_type="identity-provider-lifecycle",
            action=event.action,
            provider_name=event.provider_name,
            disable_tls_verify=event.disable_tls_verify,
        )
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=severity,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"identity_provider_{event.action}",
            event_message=f"Identity provider {event.action}: {event.provider_name}",
            source_component="syntara.identity_providers",
            structured_data=data,
            resource_urn=f"urn:syntara:identity_provider:{event.provider_id}",
            resource_name=event.provider_name,
        )
