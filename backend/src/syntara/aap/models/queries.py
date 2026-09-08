"""Query parameter models for AAP proxy endpoints."""

from uuid import UUID

from pydantic import BaseModel, Field

# Cap user-supplied text to prevent excessively long upstream queries.
_MAX_SEARCH_LENGTH = 200


class AAPBaseQuery(BaseModel):
    """Common query params for all AAP proxy endpoints.

    ``integration_id`` and ``credential_id`` are optional. Omit both when a
    single visible AAP integration exists; with multiple integrations, pass
    ``integration_id`` (``credential_id`` still defaults to that integration's
    management credential).
    """

    search: str | None = Field(default=None, max_length=_MAX_SEARCH_LENGTH, description="Search filter")
    page_size: int = Field(default=50, ge=1, le=200, description="Max results to return")
    credential_id: UUID | None = Field(
        default=None,
        description="Optional Orchestrator credential ID for Ansible Automation Platform Controller authentication. "
        "If omitted, the selected integration's management credential is used. "
        'Credential must be of type "Ansible Automation Platform". '
        "Must be a valid UUID format.",
    )
    integration_id: UUID | None = Field(
        default=None,
        description="Optional Ansible Automation Platform Gateway integration ID for connection URL resolution. "
        "If omitted, the unique visible enabled AAP integration is used. "
        "Required when more than one AAP integration is visible. "
        "Must be a valid UUID format.",
    )


class AAPResourceQuery(AAPBaseQuery):
    """Query params for org-scoped AAP resources."""

    organization: str | None = Field(
        default=None, max_length=_MAX_SEARCH_LENGTH, description="Filter by organization name"
    )
