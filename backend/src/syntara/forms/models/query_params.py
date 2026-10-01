"""Query parameter models for forms endpoints."""

from uuid import UUID

from sqlmodel import Field

from syntara.core.models.base import BaseListParams
from syntara.forms.models.api_models import FormPromptStatus


class FormPromptListParams(BaseListParams):
    """Query parameters for form prompt list endpoint.

    Extends BaseListParams with form-prompt-specific filtering options.

    Attributes:
        limit: Maximum number of results per page (from BaseListParams)
        cursor: Pagination cursor (from BaseListParams)
        sort: Sort parameter (from BaseListParams)
        include_total: Include total count in response (from BaseListParams)
        status: Filter by form prompt status
        execution_id: Filter by parent execution ID

    """

    status: FormPromptStatus | None = Field(
        default=None,
        description="Filter by form prompt status (pending, submitted, expired, cancelled)",
    )

    execution_id: UUID | None = Field(
        default=None,
        description="Filter by parent execution ID",
    )
