"""Runtime settings domain events and audit handlers.

Emits audit trail events for individual and bulk setting changes.

Requirements: AAP-74712
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class SettingChangeEvent:
    """Domain event fired when a single runtime setting is changed."""

    setting: str
    old_value: str | None = field(default=None)
    new_value: str | None = field(default=None)
    category: str | None = field(default=None)
    value_type: str | None = field(default=None)
    version: int = field(default=0)
    resource_name: str | None = field(default=None)
    error_type: str | None = field(default=None)


@dataclass
class SettingBulkChangeEvent:
    """Domain event fired when multiple settings are changed atomically."""

    settings: list[str]
    change_count: int
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Audit handlers (produce AuditEvent for persistence)
# ---------------------------------------------------------------------------


class SettingChangeHandler(AuditEventHandler[SettingChangeEvent]):
    """Maps a SettingChangeEvent to an AuditEvent."""

    def handle(self, event: SettingChangeEvent) -> AuditEvent:
        """Map a SettingChangeEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="setting-changed",
            setting=event.setting,
            old_value=event.old_value,
            new_value=event.new_value,
            category=event.category,
            value_type=event.value_type,
            version=event.version,
        )
        if is_error:
            data.error_type = event.error_type

        resource_urn = (
            f"urn:syntara:setting:{quote(event.category, safe='')}:{quote(event.setting, safe='')}"
            if event.category
            else f"urn:syntara:setting:{quote(event.setting, safe='')}"
        )

        return AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action="setting_changed",
            event_message=f"Setting '{event.setting}' updated",
            source_component="syntara.settings",
            structured_data=data,
            resource_urn=resource_urn,
            resource_name=event.resource_name,
        )


class SettingBulkChangeHandler(AuditEventHandler[SettingBulkChangeEvent]):
    """Maps a SettingBulkChangeEvent to an AuditEvent."""

    def handle(self, event: SettingBulkChangeEvent) -> AuditEvent:
        """Map a SettingBulkChangeEvent to a normalized AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="setting-bulk-changed",
            settings=event.settings,
            change_count=event.change_count,
        )
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.SYSTEM_OPERATION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action="setting_bulk_changed",
            event_message=f"Bulk update: {event.change_count} setting(s) changed",
            source_component="syntara.settings",
            structured_data=data,
        )
