"""Models for SubWorkflow output schema breaking changes detection."""

from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class BreakingChange(SQLModel):
    """A single breaking change detected in an output schema.

    Attributes:
        change_type: Type of breaking change (removed_output, type_change, new_required_output)
        field_path: Dotted path to the affected field
        old_type: Previous field type (for type changes)
        new_type: New field type (for type changes and new required outputs)
        description: Human-readable description

    """

    change_type: str
    field_path: str
    old_type: str | None = None
    new_type: str | None = None
    description: str

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class TriggerBreakingChanges(SQLModel):
    """Breaking changes for a single SubWorkflow Trigger.

    Attributes:
        trigger_id: ID of the trigger node
        trigger_name: Name of the trigger (if available)
        changes: List of breaking changes detected for this trigger

    """

    trigger_id: str
    trigger_name: str | None = None
    changes: list[BreakingChange]

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class BreakingChangesResponse(SQLModel):
    """Response containing all detected breaking changes.

    Attributes:
        has_breaking_changes: True if any breaking changes were detected
        triggers: List of triggers with breaking changes

    """

    has_breaking_changes: bool
    triggers: list[TriggerBreakingChanges]

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
