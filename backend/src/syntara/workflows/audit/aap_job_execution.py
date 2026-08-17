"""AAP job execution audit events and handlers.

Emits audit trail events when Syntara workflows launch, complete, or fail
AAP jobs (both job templates and workflow job templates).

Requirements: AAP-84598
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.workflows.workflow_engine.activities.aap_common import AAP_JOB_TERMINAL_STATUSES

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.stdlib.get_logger(__name__)

_SOURCE_COMPONENT = "syntara.workflows"

FAILURE_STATUSES: frozenset[str] = frozenset(AAP_JOB_TERMINAL_STATUSES - {"successful"})


def is_failure_status(status: Any) -> bool:  # noqa: ANN401
    """Return True if status represents a failed/error/canceled AAP job."""
    return isinstance(status, str) and status.lower() in FAILURE_STATUSES


def dispatch_audit_event(event: object) -> None:
    """Dispatch an audit event, swallowing exceptions to avoid breaking the activity."""
    try:
        AuditEventDispatcher.dispatch(event)
    except Exception:
        logger.exception("Failed to dispatch audit event", event_type=type(event).__qualname__)


def _build_resource_urn(node_type: str, job_id: int | None) -> str | None:
    if job_id is None:
        return None
    prefix = "workflow_job" if node_type == "aap_workflow_job_template" else "job"
    return f"urn:syntara:aap:{prefix}:{job_id}"


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass
class AAPJobLaunchedEvent:
    """Domain event fired when a Syntara workflow launches an AAP job."""

    execution_id: UUID
    node_type: str
    job_template_id: int
    job_id: int
    job_url: str
    base_url: str
    job_template_name: str | None = field(default=None)
    integration_id: UUID | None = field(default=None)
    actor_id: UUID | None = field(default=None)
    actor_username: str | None = field(default=None)


@dataclass
class AAPJobCompletedEvent:
    """Domain event fired when an AAP job launched by a workflow completes successfully."""

    execution_id: UUID
    node_type: str
    job_template_id: int
    job_id: int
    job_url: str
    job_status: str
    duration_ms: int | None = field(default=None)
    artifacts: dict[str, Any] | None = field(default=None)
    actor_id: UUID | None = field(default=None)
    actor_username: str | None = field(default=None)


@dataclass
class AAPJobFailedEvent:
    """Domain event fired when an AAP job launched by a workflow fails, errors, or is canceled."""

    execution_id: UUID
    node_type: str
    job_template_id: int
    job_status: str
    job_id: int | None = field(default=None)
    job_url: str | None = field(default=None)
    duration_ms: int | None = field(default=None)
    error_type: str | None = field(default=None)
    error_message: str | None = field(default=None)
    actor_id: UUID | None = field(default=None)
    actor_username: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Dispatch helpers (shared by both activity files)
# ---------------------------------------------------------------------------


def emit_launched(
    exec_uuid: UUID | None,
    template_id: int | None,
    *,
    job_id: int,
    job_url: str,
    base_url: str,
    node_type: str,
    job_template_name: str | None = None,
    actor_id: UUID | None = None,
) -> None:
    """Emit a job-launched audit event if execution_id and template_id are known."""
    if exec_uuid is None or template_id is None:
        return
    dispatch_audit_event(
        AAPJobLaunchedEvent(
            execution_id=exec_uuid,
            node_type=node_type,
            job_template_id=template_id,
            job_id=job_id,
            job_url=job_url,
            base_url=base_url,
            job_template_name=job_template_name,
            actor_id=actor_id,
        )
    )


def emit_completed(
    exec_uuid: UUID | None,
    template_id: int | None,
    *,
    job_id: int,
    job_url: str,
    final_status: str,
    duration_ms: int,
    artifacts: dict[str, Any] | None,
    node_type: str,
    actor_id: UUID | None = None,
) -> None:
    """Emit a job-completed audit event if execution_id and template_id are known."""
    if exec_uuid is None or template_id is None:
        return
    dispatch_audit_event(
        AAPJobCompletedEvent(
            execution_id=exec_uuid,
            node_type=node_type,
            job_template_id=template_id,
            job_id=job_id,
            job_url=job_url,
            job_status=final_status,
            duration_ms=duration_ms,
            artifacts=artifacts,
            actor_id=actor_id,
        )
    )


def emit_failed(
    exec_uuid: UUID | None,
    template_id: int | None,
    *,
    job_status: str,
    duration_ms: int,
    node_type: str,
    job_id: int | None = None,
    job_url: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    actor_id: UUID | None = None,
) -> None:
    """Emit a job-failed audit event if execution_id and template_id are known."""
    if exec_uuid is None or template_id is None:
        return
    dispatch_audit_event(
        AAPJobFailedEvent(
            execution_id=exec_uuid,
            node_type=node_type,
            job_template_id=template_id,
            job_status=job_status,
            job_id=job_id,
            job_url=job_url,
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            actor_id=actor_id,
        )
    )


# ---------------------------------------------------------------------------
# Audit handlers
# ---------------------------------------------------------------------------


class AAPJobLaunchedHandler(AuditEventHandler[AAPJobLaunchedEvent]):
    """Maps an AAPJobLaunchedEvent to an AuditEvent."""

    def handle(self, event: AAPJobLaunchedEvent) -> AuditEvent:
        """Map an AAPJobLaunchedEvent to a normalized AuditEvent."""
        template_label = event.job_template_name or str(event.job_template_id)
        data = AuditContextData(
            data_type="aap-job-launched",
            job_template_id=event.job_template_id,
            job_template_name=event.job_template_name,
            base_url=event.base_url,
            integration_id=str(event.integration_id) if event.integration_id else None,
        )
        actor_type = PrincipalType.USER if event.actor_id else PrincipalType.SYSTEM
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="aap_job_launched",
            event_message=f"AAP job launched: {template_label} (job {event.job_id})",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            execution_id=event.execution_id,
            resource_urn=_build_resource_urn(event.node_type, event.job_id),
            actor_id=event.actor_id,
            actor_type=actor_type,
            actor_username=event.actor_username,
        )


class AAPJobCompletedHandler(AuditEventHandler[AAPJobCompletedEvent]):
    """Maps an AAPJobCompletedEvent to an AuditEvent."""

    def handle(self, event: AAPJobCompletedEvent) -> AuditEvent:
        """Map an AAPJobCompletedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="aap-job-completed",
            job_status=event.job_status,
            duration_ms=event.duration_ms,
            artifacts=event.artifacts,
        )
        actor_type = PrincipalType.USER if event.actor_id else PrincipalType.SYSTEM
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="aap_job_completed",
            event_message=f"AAP job {event.job_id} completed with status: {event.job_status}",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            execution_id=event.execution_id,
            resource_urn=_build_resource_urn(event.node_type, event.job_id),
            actor_id=event.actor_id,
            actor_type=actor_type,
            actor_username=event.actor_username,
        )


class AAPJobFailedHandler(AuditEventHandler[AAPJobFailedEvent]):
    """Maps an AAPJobFailedEvent to an AuditEvent."""

    def handle(self, event: AAPJobFailedEvent) -> AuditEvent:
        """Map an AAPJobFailedEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="aap-job-failed",
            job_status=event.job_status,
            duration_ms=event.duration_ms,
            error_type=event.error_type,
            error_message=event.error_message,
        )
        actor_type = PrincipalType.USER if event.actor_id else PrincipalType.SYSTEM
        job_label = f"job {event.job_id}" if event.job_id else "job"
        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="aap_job_failed",
            event_message=f"AAP {job_label} failed with status: {event.job_status}",
            source_component=_SOURCE_COMPONENT,
            structured_data=data,
            execution_id=event.execution_id,
            resource_urn=_build_resource_urn(event.node_type, event.job_id),
            actor_id=event.actor_id,
            actor_type=actor_type,
            actor_username=event.actor_username,
        )
