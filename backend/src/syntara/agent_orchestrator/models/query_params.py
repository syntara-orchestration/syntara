"""Query parameter models for agent orchestrator endpoints."""

import re
from uuid import UUID

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from syntara.agent_orchestrator.models.invocation import InvocationStatus
from syntara.core.exceptions import SafeValueError
from syntara.core.models.base import BaseListParams


class InvocationListParams(BaseListParams):
    """Query parameters for invocation list endpoint."""

    status: InvocationStatus | None = Field(default=None, description="Filter by invocation status")
    created_by: UUID | None = Field(default=None, description="Filter by creator UUID")
    session_id: str | None = Field(default=None, description="Filter by session ID")
    prompt: str | None = Field(default=None, description="Filter by prompt text (substring match)")


class StreamingQueryParams(SQLModel):
    """Query parameters for WebSocket streaming endpoint.

    Validates query parameters for invocation event streaming to prevent
    injection attacks and ensure proper format.

    Attributes:
        replay_count: Number of historical events to replay on connection.
                     Can be "all" for complete history, "0" for live-only,
                     or a numeric string (non-negative integer). Default: "10".
                     Note: Values > 1000 will be capped at 1000 by the streaming layer.
        last_event_id: Optional Cache stream event ID to resume from.
                      Format: "timestamp-sequence" (e.g., "1691431234567-42").
                      Special values: "0" (start from beginning), "$" (only new events).
                      Takes precedence over replay_count.

    """

    replay_count: str = Field(
        default="10", description="Number of historical events to replay ('all', '0', or non-negative integer)"
    )
    last_event_id: str | None = Field(default=None, description="Cache stream event ID to resume from")

    @field_validator("replay_count")
    @classmethod
    def validate_replay_count(cls, v: str) -> str:
        """Validate replay_count is valid.

        Args:
            v: replay_count value to validate

        Returns:
            Validated replay_count value

        Raises:
            ValueError: If replay_count is invalid

        """
        # Allow special string values
        if v in ("all", "0"):
            return v

        # Validate numeric values (must be non-negative integer)
        try:
            count = int(v)
        except ValueError as e:
            msg = f"replay_count must be 'all', '0', or a non-negative integer string, got: {v}"
            raise SafeValueError(msg) from e

        if count < 0:
            msg = "replay_count must be non-negative"
            raise SafeValueError(msg)

        return v

    @field_validator("last_event_id")
    @classmethod
    def validate_last_event_id(cls, v: str | None) -> str | None:
        """Validate last_event_id format.

        Args:
            v: last_event_id value to validate

        Returns:
            Validated last_event_id value

        Raises:
            ValueError: If last_event_id format is invalid

        """
        if v is None:
            return v

        # Allow special values
        if v in ("0", "$"):
            return v

        # Validate stream ID format (timestamp-sequence like 1691431234567-42)
        if not re.match(r"^\d+-\d+$", v):
            msg = f"last_event_id must be in format 'timestamp-sequence' (e.g., '1691431234567-42'), got: {v}"
            raise SafeValueError(msg)

        return v
