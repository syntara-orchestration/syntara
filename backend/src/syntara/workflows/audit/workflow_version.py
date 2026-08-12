"""Workflow version domain events and audit handlers.

Covers version creation, publish, unpublish, restore, and export operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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


_SOURCE_COMPONENT = "syntara.workflows"

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class WorkflowVersionCreatedEvent:
    """Domain event fired when a new workflow version is created."""

    workflow_id: UUID
    version: int
    workflow_name: str
    change_summary: dict[str, Any] | None = field(default=None)


@dataclass
class WorkflowVersionExportedEvent:
    """Domain event fired when a workflow version is exported."""

    workflow_id: UUID
    version: int
    workflow_name: str


@dataclass
class WorkflowVersionPublishedEvent:
    """Domain event fired when a workflow version is published."""

    workflow_id: UUID
    version: int
    workflow_name: str
    project_id: UUID | None = field(default=None)
    error_type: str | None = field(default=None)


@dataclass
class WorkflowVersionUnpublishedEvent:
    """Domain event fired when a workflow is unpublished."""

    workflow_id: UUID
    version: int
    workflow_name: str
    project_id: UUID | None = field(default=None)
    error_type: str | None = field(default=None)


@dataclass
class WorkflowVersionRestoredEvent:
    """Domain event fired when a workflow version is restored from a previous version."""

    workflow_id: UUID
    restored_from_version: int
    new_version: int
    workflow_name: str
    project_id: UUID | None = field(default=None)
    error_type: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Audit handlers
# ---------------------------------------------------------------------------


class WorkflowVersionCreatedHandler(AuditEventHandler[WorkflowVersionCreatedEvent]):
    """Records an audit entry when a new workflow version is created."""

    def handle(self, event: WorkflowVersionCreatedEvent) -> AuditEvent:
        """Map a WorkflowVersionCreatedEvent to an AuditEvent."""
        data = AuditContextData(
            data_type="workflow-version-created",
            version=event.version,
        )
        if event.change_summary:
            data.change_summary = event.change_summary

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="workflow_version_created",
            event_message=f"Workflow version {event.version} created",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )


class WorkflowVersionPublishedHandler(AuditEventHandler[WorkflowVersionPublishedEvent]):
    """Records an audit entry when a workflow version is published."""

    def handle(self, event: WorkflowVersionPublishedEvent) -> AuditEvent:
        """Map a WorkflowVersionPublishedEvent to an AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="workflow-version-published",
            version=event.version,
            workflow_name=event.workflow_name,
        )
        if event.project_id is not None:
            data.project_id = str(event.project_id)
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action="workflow_version_published",
            event_message=f"Workflow version {event.version} published",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )


class WorkflowVersionUnpublishedHandler(AuditEventHandler[WorkflowVersionUnpublishedEvent]):
    """Records an audit entry when a workflow is unpublished."""

    def handle(self, event: WorkflowVersionUnpublishedEvent) -> AuditEvent:
        """Map a WorkflowVersionUnpublishedEvent to an AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="workflow-version-unpublished",
            version=event.version,
            workflow_name=event.workflow_name,
        )
        if event.project_id is not None:
            data.project_id = str(event.project_id)
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action="workflow_version_unpublished",
            event_message=f"Workflow version {event.version} unpublished",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )


class WorkflowVersionRestoredHandler(AuditEventHandler[WorkflowVersionRestoredEvent]):
    """Records an audit entry when a workflow version is restored."""

    def handle(self, event: WorkflowVersionRestoredEvent) -> AuditEvent:
        """Map a WorkflowVersionRestoredEvent to an AuditEvent."""
        is_error = event.error_type is not None

        data = AuditContextData(
            data_type="workflow-version-restored",
            restored_from_version=event.restored_from_version,
            new_version=event.new_version,
            workflow_name=event.workflow_name,
        )
        if event.project_id is not None:
            data.project_id = str(event.project_id)
        if is_error:
            data.error_type = event.error_type

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action="workflow_version_restored",
            event_message=(
                f"Workflow restored from version {event.restored_from_version} as version {event.new_version}"
            ),
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )


class WorkflowVersionExportedHandler(AuditEventHandler[WorkflowVersionExportedEvent]):
    """Records an audit entry when a workflow version is exported."""

    def handle(self, event: WorkflowVersionExportedEvent) -> AuditEvent:
        """Map a WorkflowVersionExportedEvent to an AuditEvent."""
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="workflow_version_exported",
            event_message=f"Workflow version {event.version} exported",
            source_component=_SOURCE_COMPONENT,
            structured_data=AuditContextData(
                data_type="workflow-version-exported",
                version=event.version,
            ),
            workflow_id=event.workflow_id,
            resource_urn=f"urn:syntara:workflow:{event.workflow_id}",
            resource_name=event.workflow_name,
        )
