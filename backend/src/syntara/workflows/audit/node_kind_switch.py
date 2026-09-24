"""Node-kind kill switch — domain event and audit handler (ANSTRAT-1750).

Fired when an administrator switches a workflow node kind on or off
platform-wide.  Mirrors the settings-change audit trail: the switch is stored
in the ``workflows.disabled_node_kinds`` runtime setting, so a
``SettingChangeEvent`` is emitted too; this event records the node-kind
intent explicitly so the audit trail is searchable by kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import quote

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.utils import resolve_actor_type

if TYPE_CHECKING:
    from uuid import UUID


@dataclass
class NodeKindSwitchEvent:
    """Domain event fired when a node kind is enabled or disabled platform-wide."""

    kind: str
    enabled: bool
    disabled_kinds: list[str]
    actor_id: UUID | None = field(default=None)
    actor_username: str | None = field(default=None)
    error_type: str | None = field(default=None)


class NodeKindSwitchHandler(AuditEventHandler[NodeKindSwitchEvent]):
    """Maps a NodeKindSwitchEvent to an AuditEvent."""

    def handle(self, event: NodeKindSwitchEvent) -> AuditEvent:
        """Map a NodeKindSwitchEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None
        action = "enabled" if event.enabled else "disabled"

        data = AuditContextData(
            data_type="node-kind-switch",
            kind=event.kind,
            enabled=event.enabled,
            disabled_kinds=event.disabled_kinds,
        )
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"node_kind.{action}",
            event_message=f"Workflow node kind '{event.kind}' {action}",
            source_component="syntara.workflows",
            structured_data=data,
            actor_id=event.actor_id,
            actor_type=resolve_actor_type(actor_id=event.actor_id),
            actor_username=event.actor_username,
            resource_urn=f"urn:syntara:workflow_node:{quote(event.kind, safe='')}",
            resource_name=event.kind,
        )
