"""Explicit public configuration and non-consuming preflight contracts."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Query
from sqlmodel import Field, SQLModel

from syntara.core.models.base import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.eventstreams.adapters.source_configuration import SourceConfiguration


class EventSubscriptionSourceRead(SQLModel):
    """The current source's non-secret configuration."""

    id: UUID
    generation: int
    integration_id: UUID | None
    transport: str
    configuration: SourceConfiguration


class EventSubscriptionRead(SQLModel):
    """Currently available published configuration; no runtime-health claims."""

    id: UUID
    workflow_id: UUID
    project_id: UUID
    trigger_node_id: str
    published_version_id: UUID
    configuration_revision: int
    runtime_credential_id: UUID | None
    input_schema: dict[str, Any] | None
    desired_enabled: bool
    paused: bool
    created_at: datetime
    updated_at: datetime
    source: EventSubscriptionSourceRead


EventSubscriptionListResponse = ResourcesResponse[EventSubscriptionRead]


class EventSubscriptionListParams(BaseListParams):
    """Standard bounded pagination with optional transport selection."""

    transport: Annotated[Literal["kafka"] | None, Query(json_schema_extra={"x-query-param": True})] = None


class EventSubscriptionTestResponse(SQLModel):
    """Success proves connectivity and topic metadata only, never runtime ACLs."""

    success: bool
    checked_at: datetime
    connection: Literal["verified", "failed", "unverified"] = "unverified"
    topic_metadata: Literal["verified", "failed", "unverified"] = "unverified"
    topic_read: Literal["unverified"] = "unverified"
    group_access: Literal["unverified"] = "unverified"
    error_code: str | None = Field(default=None, description="Sanitized failure code; no broker error text")
