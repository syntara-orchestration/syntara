"""Models for stored Execution Plane workflow-definition migrations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MigrationCredentialBinding(BaseModel):
    """Typed credential binding used by stored workflow migrations."""

    model_config = ConfigDict(extra="forbid")

    credential_recipe_id: str = Field(min_length=1)
    credential_ref: str = Field(min_length=1)

    @field_validator("credential_ref")
    @classmethod
    def validate_credential_ref(cls, value: str) -> str:
        """Require a Syntara credential UUID while preserving its stored representation."""
        try:
            UUID(value)
        except ValueError as error:
            message = "credential_ref must contain a valid UUID"
            raise ValueError(message) from error
        return value


class MigrationNodeParameters(BaseModel):
    """Typed node parameters used by stored workflow migrations."""

    model_config = ConfigDict(extra="allow")

    credential_id: str | None = None
    credential_bindings: list[MigrationCredentialBinding] | None = None

    @field_validator("credential_id")
    @classmethod
    def validate_credential_id(cls, value: str | None) -> str | None:
        """Require a Syntara credential UUID while preserving its stored representation."""
        if value is None:
            return value
        try:
            UUID(value)
        except ValueError as error:
            message = "credential_id must contain a valid UUID"
            raise ValueError(message) from error
        return value


class MigrationWorkflowNode(BaseModel):
    """Typed workflow node used by stored workflow migrations."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    parameters: MigrationNodeParameters


class MigrationWorkflowDefinition(BaseModel):
    """Typed workflow definition used by stored workflow migrations."""

    model_config = ConfigDict(extra="allow")

    nodes: list[MigrationWorkflowNode]
