"""Combined read models for the integrations catalog, preserving the original v1 resource."""

from typing import Literal

from sqlmodel import Field

from syntara.core.models.pagination import ResourcesResponse
from syntara.integrations.models.kafka_integration import KafkaIntegrationListParams, KafkaIntegrationRead
from syntara.integrations.models.legacy_integration import IntegrationRead


class IntegrationCatalogListParams(KafkaIntegrationListParams):
    """Filter and paginate the combined integration catalog."""

    integration_type: Literal["mcp_server", "llm_provider", "ansible_automation_platform", "kafka"] | None = Field(
        default=None, description="Filter by integration type"
    )


class IntegrationCatalogListResponse(ResourcesResponse[IntegrationRead | KafkaIntegrationRead]):
    """Paginated integrations of every supported type."""
