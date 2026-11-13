"""Combined read models for the integrations catalog, preserving the original v1 resource."""

from typing import Any, Literal
from uuid import UUID

from sqlmodel import Field

from syntara.core.models.base import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.integrations.models.integration import IntegrationScope, IntegrationStatus
from syntara.integrations.models.kafka_integration import KafkaIntegrationRead
from syntara.integrations.models.legacy_integration import IntegrationRead


def _equality_filter_schema(schema: dict[str, Any]) -> None:
    """Declare the scalar shorthand and the shared filter parser's eq operator."""
    value_schema = schema.copy()
    schema.clear()
    schema["allOf"] = [value_schema, {"type": "object", "properties": {"eq": value_schema}}]


class IntegrationCatalogListParams(BaseListParams):
    """Filter and paginate the combined integration catalog."""

    validation_status: IntegrationStatus | None = Field(
        default=None,
        description="Filter by validation status",
        schema_extra={"json_schema_extra": _equality_filter_schema},
    )
    enabled: bool | None = Field(
        default=None,
        description="Filter by enabled status",
        schema_extra={"json_schema_extra": _equality_filter_schema},
    )
    scope: IntegrationScope | None = Field(
        default=None,
        description="Filter by visibility scope",
        schema_extra={"json_schema_extra": _equality_filter_schema},
    )
    management_credential_id: UUID | None = Field(
        default=None,
        description="Filter by management credential ID",
        schema_extra={"json_schema_extra": _equality_filter_schema},
    )
    project_id: UUID | None = Field(
        default=None,
        description="Filter to integrations that are global or assigned to this project. "
        "Restricted to projects the user has RBAC access to; querying inaccessible projects "
        "returns only global integrations.",
        schema_extra={"json_schema_extra": {"x-query-param": True}},
    )
    integration_type: Literal["mcp_server", "llm_provider", "ansible_automation_platform", "kafka"] | None = Field(
        default=None,
        description="Filter by integration type",
        schema_extra={"json_schema_extra": _equality_filter_schema},
    )


class IntegrationCatalogListResponse(ResourcesResponse[IntegrationRead | KafkaIntegrationRead]):
    """Paginated integrations of every supported type."""
