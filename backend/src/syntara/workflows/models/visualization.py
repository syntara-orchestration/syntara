"""Visualization streaming event data models.

This module contains typed models for WebSocket streaming events related to
workflow execution visualization, conforming to the AsyncAPI specification.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class JsonPatchOperation(BaseModel):
    """JSON Patch operation according to RFC 6902.

    Represents a single operation in a JSON Patch document.

    Attributes:
        op: The operation type
        path: JSON Pointer to the target location
        value: Value for add/replace/test operations
        from_: Source location for move/copy operations

    """

    op: Literal["add", "remove", "replace", "move", "copy", "test"] = Field(
        description="The operation type",
        examples=["replace", "add"],
    )
    path: str = Field(
        description="JSON Pointer to the target location",
        examples=["/activities/0/status", "/activities/1/completed_at"],
    )
    value: Any | None = Field(
        default=None,
        description="Value for add/replace/test operations",
        examples=["completed", "2024-01-20T10:35:00Z"],
    )
    from_: str | None = Field(
        default=None,
        alias="from",
        description="Source location for move/copy operations",
        examples=["/activities/0"],
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "op": "replace",
                    "path": "/activities/0/status",
                    "value": "completed",
                },
                {
                    "op": "add",
                    "path": "/activities/0/completed_at",
                    "value": "2024-01-20T10:35:00Z",
                },
            ]
        },
    )


class ExecutionSnapshotMessage(BaseModel):
    """WebSocket message for execution snapshots.

    Sent at the beginning (initial_snapshot) and end (final_snapshot) of execution
    streaming to provide full state for synchronization.

    Attributes:
        type: Message type discriminator
        execution_id: Execution identifier
        event_id: Redis Stream event ID for replay support
        execution: Full execution data with activities (same schema as REST API)
        timestamp: When this message was generated

    """

    type: Literal["initial_snapshot", "final_snapshot"] = Field(
        description="Message type discriminator",
        examples=["initial_snapshot", "final_snapshot"],
    )
    execution_id: str = Field(
        description="Execution identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    event_id: str = Field(
        description="Redis Stream event ID for replay support",
        examples=["1642680000000-0", "1642680123456-1"],
    )
    execution: dict[str, Any] = Field(
        description="Full execution data with activities (same schema as REST API)",
        examples=[
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "running",
                "activities": [
                    {
                        "activity_id": "send_email",
                        "status": "running",
                        "started_at": "2024-01-20T10:30:00Z",
                    }
                ],
            }
        ],
    )
    timestamp: datetime = Field(
        description="When this message was generated",
        examples=["2024-01-20T10:30:00Z"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "initial_snapshot",
                    "execution_id": "123e4567-e89b-12d3-a456-426614174000",
                    "event_id": "1642680000000-0",
                    "execution": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "status": "running",
                        "activities": [],
                    },
                    "timestamp": "2024-01-20T10:30:00Z",
                }
            ]
        }
    )


class ActivityPatchMessage(BaseModel):
    """WebSocket message for incremental activity updates.

    Contains JSON Patch operations to apply to the activities array,
    enabling efficient incremental updates.

    Attributes:
        type: Message type discriminator (always "activity_patch")
        execution_id: Execution identifier
        event_id: Redis Stream event ID for replay support
        ops: JSON Patch operations to apply
        timestamp: When this message was generated

    """

    type: Literal["activity_patch"] = Field(
        description="Message type discriminator",
        examples=["activity_patch"],
    )
    execution_id: str = Field(
        description="Execution identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    event_id: str = Field(
        description="Redis Stream event ID for replay support",
        examples=["1642680123456-1"],
    )
    ops: list[JsonPatchOperation] = Field(
        description="JSON Patch operations to apply",
        examples=[
            [
                {
                    "op": "replace",
                    "path": "/activities/0/status",
                    "value": "completed",
                }
            ]
        ],
    )
    timestamp: datetime = Field(
        description="When this message was generated",
        examples=["2024-01-20T10:35:00Z"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "activity_patch",
                    "execution_id": "123e4567-e89b-12d3-a456-426614174000",
                    "event_id": "1642680123456-1",
                    "ops": [
                        {
                            "op": "replace",
                            "path": "/activities/0/status",
                            "value": "completed",
                        }
                    ],
                    "timestamp": "2024-01-20T10:35:00Z",
                }
            ]
        }
    )


class ExecutionPatchMessage(BaseModel):
    """WebSocket message for execution-level status updates.

    Contains JSON Patch operations to apply to execution fields (e.g. status),
    enabling lightweight real-time updates without resending the full snapshot.

    Attributes:
        type: Message type discriminator (always "execution_patch")
        execution_id: Execution identifier
        event_id: Redis Stream event ID for replay support
        ops: JSON Patch operations to apply
        timestamp: When this message was generated

    """

    type: Literal["execution_patch"] = Field(
        description="Message type discriminator",
        examples=["execution_patch"],
    )
    execution_id: str = Field(
        description="Execution identifier",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    event_id: str = Field(
        description="Redis Stream event ID for replay support",
        examples=["1642680123456-1"],
    )
    ops: list[JsonPatchOperation] = Field(
        description="JSON Patch operations to apply to execution fields",
        examples=[
            [
                {
                    "op": "replace",
                    "path": "/status",
                    "value": "paused",
                }
            ]
        ],
    )
    timestamp: datetime = Field(
        description="When this message was generated",
        examples=["2024-01-20T10:35:00Z"],
    )
