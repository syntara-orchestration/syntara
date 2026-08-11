"""SQLModel schemas for agent responses.

Defines response models for different agent types.
"""

from typing import Any, Literal

from sqlmodel import Field, SQLModel


class BaseAgentResponse(SQLModel):
    """Base response model for all agents.

    Provides common fields that all agent responses must include.
    Concrete agent response types should inherit from this class.
    """

    content: str | dict[str, Any] = Field(
        ...,
        description="The main content of the agent's response (str for text, dict for structured output)",
    )
    response_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the response",
        alias="metadata",
    )


class GenericAgentResponse(BaseAgentResponse):
    """Response model for GenericAgent.

    Used when GenericAgent answers an information query directly
    without generating a workflow.
    """

    type: Literal["answer"] = Field(
        default="answer",
        description="Response type (always 'answer' for GenericAgent)",
    )
