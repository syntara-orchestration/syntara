"""Workflow validation request model."""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator
from sqlmodel import SQLModel

from syntara.core.jsonb_limits import validate_workflow_definition_json


class WorkflowValidateRequest(SQLModel):
    """Request body for the workflow validation endpoint.

    The definition is accepted as a raw dict so that structurally invalid
    definitions reach the application-level validator for richer error
    reporting with node-level attribution.
    """

    workflow_definition: dict[str, Any] = Field(..., description="Workflow definition to validate")

    @field_validator("workflow_definition", mode="before")
    @classmethod
    def validate_workflow_definition_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_workflow_definition_json(v)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
