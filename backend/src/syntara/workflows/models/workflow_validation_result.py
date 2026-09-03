"""Workflow validation request model."""

from typing import Annotated, Any, ClassVar

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel

from syntara.core.jsonb_limits import WorkflowDefinitionSizeValidator


class WorkflowValidateRequest(SQLModel):
    """Request body for the workflow validation endpoint.

    The definition is accepted as a raw dict so that structurally invalid
    definitions reach the application-level validator for richer error
    reporting with node-level attribution.
    """

    workflow_definition: Annotated[dict[str, Any], WorkflowDefinitionSizeValidator] = Field(
        ..., description="Workflow definition to validate"
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
