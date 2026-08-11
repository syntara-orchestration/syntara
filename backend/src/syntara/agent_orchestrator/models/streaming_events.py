"""Streaming event data models.

This module contains typed models for streaming event data payloads,
conforming to the AsyncAPI specification for WebSocket events.
Also includes models for persisted agent trace data.
"""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class TraceStep(SQLModel):
    """Single step in a persisted agent execution trace."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    type: str = Field(description="Step type: reasoning, tool_call, tool_result, or final_answer")
    timestamp: str = Field(description="ISO 8601 timestamp")
    content: str = Field(description="Human-readable description of this step")
    duration_ms: int | None = Field(default=None, description="Step duration in milliseconds")
    tokens: int | None = Field(default=None, description="Token count for this step")
    tool_name: str | None = Field(default=None, description="Tool name (tool_call and tool_result)")
    tool_input: dict[str, Any] | None = Field(default=None, description="Tool input args (tool_call)")
    tool_output: str | None = Field(default=None, description="Tool output (tool_result)")
    status: str | None = Field(default=None, description="Tool execution status: success or failed (tool_result)")
    call_id: str | None = Field(
        default=None, description="Unique call identifier for matching tool_call/tool_result pairs"
    )


class AgentTrace(SQLModel):
    """Persisted agent execution trace with accumulated steps."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    model: str = Field(description="LLM model used for this execution")
    total_tokens: int = Field(default=0, description="Total tokens across all steps")
    total_duration_ms: int = Field(default=0, description="Total execution duration in milliseconds")
    steps: list[TraceStep] = Field(default_factory=list, description="Ordered trace steps")


class DeltaEventData(SQLModel):
    """Data payload for delta streaming events.

    Represents individual content chunks delivered during LLM response generation.

    Attributes:
        delta: The actual delta content chunk

    """

    delta: str = Field(
        description="The actual delta content chunk",
        min_length=1,
        examples=["Hello", " world", "!"],
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {"delta": "Hello"},
                {"delta": " world"},
                {"delta": "!"},
            ]
        },
    )  # type: ignore[assignment]


class CancelledEventData(SQLModel):
    """Data payload for streaming cancellation events.

    Indicates that streaming was cancelled before completion.

    Attributes:
        reason: Why the streaming was cancelled

    """

    reason: str = Field(
        description="Why the streaming was cancelled",
        min_length=1,
        max_length=200,
        examples=["user_cancelled", "timeout", "server_shutdown", "llm_error"],
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {"reason": "user_cancelled"},
                {"reason": "timeout"},
                {"reason": "server_shutdown"},
                {"reason": "llm_error"},
            ]
        },
    )  # type: ignore[assignment]


class CompletionEventData(SQLModel):
    """Data payload for streaming completion events.

    Empty object - the event_type itself indicates successful completion.
    Defined as a class for consistency and type safety.

    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {},
            ]
        },
    )  # type: ignore[assignment]


class ToolCallEventData(SQLModel):
    """Data payload for tool call start events.

    Indicates that the LLM has requested a tool call and execution is starting.

    Attributes:
        tool_name: Name of the tool being called
        tool_input: Input arguments passed to the tool

    """

    tool_name: str = Field(
        description="Name of the tool being called",
        min_length=1,
        examples=["calculator", "weather_lookup"],
    )
    tool_input: dict[str, Any] = Field(
        default_factory=dict,
        description="Input arguments passed to the tool",
        examples=[{"a": 5, "b": 3}, {"city": "London"}],
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {"tool_name": "calculator", "tool_input": {"a": 5, "b": 3}},
                {"tool_name": "weather_lookup", "tool_input": {"city": "London"}},
            ]
        },
    )  # type: ignore[assignment]


class ToolResultEventData(SQLModel):
    """Data payload for tool execution result events.

    Contains the result of a tool execution.

    Attributes:
        tool_name: Name of the tool that was executed
        tool_output: Output/result from the tool execution

    """

    tool_name: str = Field(
        description="Name of the tool that was executed",
        min_length=1,
        examples=["calculator", "weather_lookup"],
    )
    tool_output: str = Field(
        description="Output/result from the tool execution",
        examples=["8", "Sunny, 22°C"],
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        json_schema_extra={
            "examples": [
                {"tool_name": "calculator", "tool_output": "8"},
                {"tool_name": "weather_lookup", "tool_output": "Sunny, 22°C"},
            ]
        },
    )  # type: ignore[assignment]
