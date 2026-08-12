"""Workflow validation request model."""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class WorkflowValidateRequest(SQLModel):
    """Request body for the workflow validation endpoint.

    The definition is accepted as a raw dict so that structurally invalid
    definitions reach the application-level validator for richer error
    reporting with node-level attribution.
    """

    workflow_definition: dict[str, Any] = Field(..., description="Workflow definition to validate")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
