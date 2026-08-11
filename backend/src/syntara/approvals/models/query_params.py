"""Query parameter models for approvals endpoints."""

from uuid import UUID

from sqlmodel import Field

from syntara.approvals.models import ApprovalRequestStatus
from syntara.core.models.base import BaseListParams


class ApprovalListParams(BaseListParams):
    """Query parameters for approval list endpoint.

    Extends BaseListParams with approval-specific filtering options.

    Attributes:
        limit: Maximum number of results per page (from BaseListParams)
        cursor: Pagination cursor (from BaseListParams)
        sort: Sort parameter (from BaseListParams)
        include_total: Include total count in response (from BaseListParams)
        status: Filter by approval status
        execution_id: Filter by parent execution ID

    """

    status: ApprovalRequestStatus | None = Field(
        default=None,
        description="Filter by approval status (pending, approved, rejected, expired, cancelled)",
    )

    execution_id: UUID | None = Field(
        default=None,
        description="Filter by parent execution ID",
    )
