"""Tool schema models."""

from typing import Any, ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class ToolSchema(SQLModel):
    """Schema definition for a tool.

    Attributes:
        name: Name of the tool
        description: Description of what the tool does
        input_schema: JSON schema defining the tool's input parameters
        output_schema: Optional JSON schema defining the tool's output format
        examples: Optional list of usage examples

    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    examples: list[dict[str, Any]] | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]
