"""Models for SubWorkflow output schema breaking changes detection."""

from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class BreakingChange(SQLModel):
    """A single breaking change detected in an output schema.

    Attributes:
        change_type: Category of output contract change.
        field_path: Dotted path to the affected public output field.
        old_type: Previous JSON Schema type, when applicable.
        new_type: Candidate JSON Schema type, when applicable.
        description: Human-readable description

    """

    change_type: str = Field(
        description=(
            "Change category, such as removed_output, type_change, new_required_output, added_output, "
            "required_output, optional_output, constraint_change, mapping_changed, or removed_trigger."
        )
    )
    field_path: str = Field(
        description="Dotted path to the affected public output field, or the trigger ID when a trigger is removed."
    )
    old_type: str | None = Field(default=None, description="Previous JSON Schema type, when applicable.")
    new_type: str | None = Field(default=None, description="Candidate JSON Schema type, when applicable.")
    description: str = Field(description="Human-readable explanation of the contract change.")
    is_breaking: bool = Field(
        default=True,
        description="Whether this change can break consumers of the published output contract.",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class TriggerBreakingChanges(SQLModel):
    """Breaking changes for a single SubWorkflow Trigger.

    Attributes:
        trigger_id: ID of the trigger node
        trigger_name: Name of the trigger (if available)
        changes: List of breaking changes detected for this trigger

    """

    trigger_id: str = Field(description="ID of the Subworkflow Trigger whose output contract changed.")
    trigger_name: str | None = Field(default=None, description="Optional display name of the Subworkflow Trigger.")
    changes: list[BreakingChange] = Field(description="Output contract changes detected for this trigger.")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class WorkflowReferenceRead(SQLModel):
    """A currently published parent workflow step that references this child."""

    workflow_id: UUID = Field(description="ID of the published parent workflow that references the child.")
    workflow_name: str = Field(description="Name of the published parent workflow.")
    workflow_version: int = Field(description="Published version number of the parent workflow.")
    step_id: str = Field(description="ID of the Sub-workflow node in the parent workflow.")
    step_name: str | None = Field(default=None, description="Optional display name of the referencing node.")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class BreakingChangesResponse(SQLModel):
    """Response containing output contract changes and visible parent references."""

    has_breaking_changes: bool = Field(description="Whether any detected output contract change is breaking.")
    triggers: list[TriggerBreakingChanges] = Field(
        description="Per-trigger groups containing breaking changes only; empty when none are breaking."
    )
    has_contract_changes: bool = Field(
        default=False,
        description="Whether any output schema or source mapping changed, including nonbreaking changes.",
    )
    contract_changes: list[TriggerBreakingChanges] = Field(
        default_factory=list,
        description="All detected per-trigger changes, including nonbreaking changes.",
    )
    parent_workflows: list[WorkflowReferenceRead] = Field(
        default_factory=list,
        description=(
            "Visible, currently published parent workflow steps referencing triggers whose output contracts changed."
        ),
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
