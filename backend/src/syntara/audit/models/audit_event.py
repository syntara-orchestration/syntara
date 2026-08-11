"""Audit event model and enums for tracking system activities."""

import re
from enum import StrEnum
from typing import Any
from uuid import UUID

import structlog
from pydantic import SerializeAsAny, field_validator
from sqlmodel import Field, SQLModel
from uuid_utils import uuid7 as _uuid7_native

from syntara.audit.models.structured_data import AuditContextData
from syntara.core.constants import FieldLimits
from syntara.core.models.principal import PrincipalType


def _uuid7() -> UUID:
    return UUID(str(_uuid7_native()))


logger = structlog.stdlib.get_logger(__name__)

# RFC 8141 URN pattern
# Format: urn:<nid>:<nss>
# - NID: 2-32 characters, starts with alphanumeric, rest can include hyphens
# - NSS: 1+ characters from RFC 8141 allowed set
#   unreserved: a-z 0-9 ( ) + , - . : = @ ; $ _ ! * ' %
#   pct-encoded: % (already included)
#   sub-delims: / ? ~ &
_URN_PATTERN = re.compile(
    r"^urn:[a-z0-9][a-z0-9-]{1,31}:[a-z0-9()+,\-.:=@;$_!*'%/?~&]+$",
    re.IGNORECASE,
)


class EventCategory(StrEnum):
    """Categories for different types of audit events."""

    USER_ACTION = "user_action"
    WORKFLOW_EVENT = "workflow_event"
    AGENT_INTERACTION = "agent_interaction"
    LLM_INTERACTION = "llm_interaction"
    LLM_TOOL_CALL = "llm_tool_call"
    LLM_REASONING = "llm_reasoning"
    API_EXECUTION = "api_execution"
    SYSTEM_OPERATION = "system_operation"
    SECURITY_EVENT = "security_event"


class EventSeverity(StrEnum):
    """Severity levels for audit events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventStatus(StrEnum):
    """Status of an audited operation."""

    SUCCESS = "success"
    ERROR = "error"


class AuditEvent(SQLModel):
    """Audit event model for tracking system activities and user actions."""

    # Core identification
    event_id: UUID = Field(default_factory=_uuid7, description="Unique identifier for the audit event")
    event_category: EventCategory = Field(description="Category of the audit event")
    event_severity: EventSeverity = Field(default=EventSeverity.INFO, description="Severity level of the audit event")
    event_status: EventStatus | None = Field(default=None, description="Status of the audited operation")
    event_action: str = Field(description="Specific action that occurred")

    # Actor and source information
    actor_id: UUID | None = Field(default=None, description="User/system/service that performed action")
    actor_type: PrincipalType | None = Field(default=None, description="Type of actor (user|system|service_account)")
    actor_username: str | None = Field(default=None, description="Username of the actor")
    source_component: str = Field(description="Component that generated event")
    resource_urn: str | None = Field(
        default=None, max_length=1024, description="RFC 8141 compliant URN identifying the resource"
    )
    resource_name: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Human-readable name of the resource at event creation time",
    )

    # Context tracking
    workflow_id: UUID | None = Field(default=None, description="Workflow identifier for workflow-scoped events")
    activity_id: str | None = Field(default=None, description="Activity identifier for activity-level events")
    execution_id: UUID | None = Field(default=None, description="Execution identifier for execution tracing")

    # Human-readable message
    event_message: str = Field(description="Human-readable description of the event")

    # Event data (sanitized)
    structured_data: SerializeAsAny[AuditContextData] = Field(description="Structured event data (sanitized)")

    @field_validator("resource_urn", mode="before")
    @classmethod
    def validate_resource_urn(cls, v: Any) -> str | None:  # noqa: ANN401
        """Validate resource_urn conforms to RFC 8141 URN format.

        RFC 8141 URN format: urn:<nid>:<nss>
        - nid (Namespace Identifier): 2-32 characters, starts with alphanumeric,
          rest can be alphanumeric or hyphen
        - nss (Namespace Specific String): 1+ characters from RFC 8141 allowed set

        If invalid, log a warning and return None to prevent storing malformed URNs.
        This ensures audit event emission never fails due to invalid URN format.

        Args:
            v: The resource_urn value to validate

        Returns:
            The validated URN string, or None if invalid or not provided

        """
        if v is None:
            return None

        if not isinstance(v, str):
            logger.warning(
                "resource_urn must be a string, dropping invalid value",
                provided_type=type(v).__name__,
            )
            return None

        if not _URN_PATTERN.match(v):
            logger.warning(
                "resource_urn does not conform to RFC 8141 URN format (urn:<nid>:<nss>), dropping invalid value",
                provided_value=v,
            )
            return None

        return v
