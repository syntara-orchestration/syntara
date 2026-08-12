"""Query parameter models for workflow-related endpoints."""

import re

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from syntara.core.exceptions import SafeValueError
from syntara.core.models.base import BaseListParams
from syntara.workflows.models.execution import ExecutionInclude


class WorkflowListParams(BaseListParams):
    """Query parameters for workflow list endpoint."""

    # Allow filtering by workflow-specific fields
    # Note: Additional query parameters are handled by the service layer
    # for complex filtering operations like created_by, is_enabled, etc.


class WorkflowVersionListParams(BaseListParams):
    """Query parameters for workflow version list endpoint."""


class ExecutionListParams(BaseListParams):
    """Query parameters for execution list endpoint."""

    # Allow filtering by execution-specific fields
    # Note: Additional query parameters are handled by the service layer
    # for complex filtering operations like workflow_id, status, etc.


class ActivityListParams(BaseListParams):
    """Query parameters for activity execution list endpoint."""


class ExecutionIncludeParams(SQLModel):
    """Query parameters for execution include functionality."""

    include: str | None = Field(
        default=None,
        description="Comma-separated list of related data to include. Valid values: workflow_definition, activities",
    )

    @field_validator("include")
    @classmethod
    def validate_include(cls, v: str | None) -> str | None:
        """Validate include parameter for correct values and no duplicates."""
        if v is None or v.strip() == "":
            return v

        # Parse the comma-separated values
        requested_include_list = [item.strip() for item in v.split(",")]
        requested_include_strings = set(requested_include_list)

        # Check for duplicate values before deduplication
        if len(requested_include_list) != len(requested_include_strings):
            msg = "Duplicate include values are not allowed"
            raise SafeValueError(msg)

        # Validate all requested includes are valid
        valid_values = {item.value for item in ExecutionInclude}
        invalid_includes = requested_include_strings - valid_values
        if invalid_includes:
            msg = (
                f"Invalid include values: {', '.join(invalid_includes)}. "
                f"Valid values are: {', '.join(sorted(valid_values))}"
            )
            raise SafeValueError(msg)

        return v

    def get_include_set(self) -> set[ExecutionInclude] | None:
        """Convert validated include string to a set of ExecutionInclude enums."""
        if self.include is None or self.include.strip() == "":
            return None

        requested_include_strings = {item.strip() for item in self.include.split(",")}
        valid_includes = {ExecutionInclude.WORKFLOW_DEFINITION, ExecutionInclude.ACTIVITIES}
        return {item for item in valid_includes if item.value in requested_include_strings}


class ExecutionStreamingQueryParams(SQLModel):
    """Query parameters for execution WebSocket streaming endpoint.

    Validates query parameters for execution event streaming to prevent
    injection attacks and ensure proper format.

    Attributes:
        replay: Optional replay parameter for event replay from Redis Streams.
               - Not specified (None): Live streaming only (new events after connection)
               - "0": Replay from beginning (includes initial snapshot)
               - "<event_id>": Replay from specific Redis stream ID (e.g., "1691431234567-5")

    """

    replay: str | None = Field(
        default=None,
        description="Replay parameter for event replay ('0' or Redis stream ID)",
    )

    @field_validator("replay")
    @classmethod
    def validate_replay(cls, v: str | None) -> str | None:
        """Validate replay parameter format.

        Args:
            v: replay value to validate

        Returns:
            Validated replay value

        Raises:
            ValueError: If replay format is invalid

        """
        if v is None:
            return v

        # Allow "0" for replay from beginning
        if v == "0":
            return v

        # Validate Redis stream ID format (timestamp-sequence like 1691431234567-42)
        if not re.match(r"^\d+-\d+$", v):
            msg = (
                f"replay must be '0' or Redis stream ID format 'timestamp-sequence' "
                f"(e.g., '1691431234567-42'), got: {v}"
            )
            raise SafeValueError(msg)

        return v
