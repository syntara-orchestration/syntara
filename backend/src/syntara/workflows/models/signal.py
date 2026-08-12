"""Signal models for workflow activity signals.

This module defines the Pydantic models for activity signal payloads and responses,
matching the OpenAPI schema definitions in openapi.yaml.
"""

from typing import Any

from pydantic import BaseModel, Field


class ActivitySignalPayload(BaseModel):
    """Generic signal payload for sending arbitrary data to a specific activity.

    This matches the ActivitySignalPayload schema in openapi.yaml.
    The signal_data field contains arbitrary JSON data whose structure depends
    on what the activity expects to receive.

    Examples:
        Simple completion signal:
        >>> payload = ActivitySignalPayload(signal_data={
        ...     "status": "completed",
        ...     "result": {"value": 42}
        ... })

        Agent execution result:
        >>> payload = ActivitySignalPayload(signal_data={
        ...     "id": "inv-123",
        ...     "status": "completed",
        ...     "result": {
        ...         "content": "Analysis complete",
        ...         "response_metadata": {"model": "claude-3.5"}
        ...     },
        ...     "timestamp": "2026-01-14T12:00:00Z"
        ... })

        Error signal:
        >>> payload = ActivitySignalPayload(signal_data={
        ...     "status": "failed",
        ...     "error": {
        ...         "message": "Execution failed",
        ...         "error_type": "AgentOrchestratorError"
        ...     }
        ... })

    """

    signal_data: dict[str, Any] = Field(
        ...,
        description="Arbitrary JSON data to send to the activity. "
        "The structure depends on what the activity expects to receive.",
        examples=[
            {
                "action": "resume",
                "status": "completed",
                "result": {"value": 42},
            }
        ],
    )

    model_config = {
        "json_schema_extra": {
            "title": "Activity Signal Payload",
            "description": "Generic signal payload for sending arbitrary data to a specific activity "
            "within a running workflow execution.",
        }
    }


class SignalResponse(BaseModel):
    """Response confirming a signal was sent to a workflow.

    This matches the SignalResponse schema in openapi.yaml.
    """

    status: str = Field(
        ...,
        description="Confirmation that the signal was successfully sent",
        pattern="^signal_sent$",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable confirmation message",
    )

    model_config = {
        "json_schema_extra": {
            "title": "Signal Response",
            "description": "Response confirming a signal was sent to a workflow",
        }
    }
