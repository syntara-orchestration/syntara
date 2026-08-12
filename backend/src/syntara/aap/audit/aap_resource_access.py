"""AAPResourceAccessEvent and AAPResourceAccessHandler for AAP-domain audit.

Tracks user access to external AAP Controller resources via the Syntara proxy.

Requirements: AAP-73903
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.utils import resolve_actor_type
from syntara.core.models.principal import PrincipalType

if TYPE_CHECKING:
    from uuid import UUID


class AAPResourceType(StrEnum):
    """AAP resource types exposed by the proxy."""

    ORGANIZATIONS = "organizations"
    JOB_TEMPLATES = "job_templates"
    WORKFLOW_JOB_TEMPLATES = "workflow_job_templates"
    INVENTORIES = "inventories"
    EXECUTION_ENVIRONMENTS = "execution_environments"
    CREDENTIALS = "credentials"
    INSTANCE_GROUPS = "instance_groups"
    LABELS = "labels"


class AAPAccessAction(StrEnum):
    """Access action performed on an AAP resource."""

    LIST = "list"
    GET = "get"


# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class AAPResourceAccessEvent:
    """Domain event emitted when a user accesses AAP resources via the proxy.

    Captures the resource type, action (list/get), result metadata, and
    whether a per-user credential was used (vs. environment-level auth).
    """

    resource_type: AAPResourceType
    action: AAPAccessAction
    user_id: UUID | None = field(default=None)
    username: str | None = field(default=None)
    result_count: int | None = field(default=None)
    resource_id: int | None = field(default=None)
    resource_name: str | None = field(default=None)
    credential_used: bool = field(default=False)
    search_filter: str | None = field(default=None)
    organization_filter: str | None = field(default=None)
    error_type: str | None = field(default=None)
    principal_type: PrincipalType | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class AAPResourceAccessHandler(AuditEventHandler[AAPResourceAccessEvent]):
    """Maps an AAPResourceAccessEvent to a normalized AuditEvent."""

    def handle(self, event: AAPResourceAccessEvent) -> AuditEvent:
        """Map an AAPResourceAccessEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        if event.action == AAPAccessAction.GET:
            action_name = f"aap_{event.resource_type}_retrieved"
            message = f"AAP {event.resource_type} {event.resource_id} retrieved"
            resource_urn = f"urn:syntara:aap:{event.resource_type}:{event.resource_id}"
        else:
            action_name = f"aap_{event.resource_type}_listed"
            count = event.result_count if event.result_count is not None else 0
            message = f"AAP {event.resource_type} listed ({count} results)"
            resource_urn = f"urn:syntara:aap:{event.resource_type}"

        if is_error:
            message = f"AAP {event.resource_type} access failed"

        data = AuditContextData(
            data_type="aap-resource-access",
            error_type=event.error_type if is_error else None,
            error_message=None,
            resource_type=event.resource_type.value,
            action=event.action.value,
            credential_used=event.credential_used,
        )
        if event.result_count is not None:
            data.result_count = event.result_count
        if event.resource_id is not None:
            data.resource_id = event.resource_id
        if event.search_filter:
            data.search_filter = event.search_filter
        if event.organization_filter:
            data.organization_filter = event.organization_filter

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=action_name,
            event_message=message,
            source_component="syntara.aap",
            structured_data=data,
            resource_urn=resource_urn,
            resource_name=event.resource_name,
            actor_id=event.user_id,
            actor_type=resolve_actor_type(actor_id=event.user_id, principal_type=event.principal_type)
            if event.user_id
            else PrincipalType.SYSTEM,
            actor_username=event.username,
        )
