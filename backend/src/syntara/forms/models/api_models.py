"""API request/response models for form endpoints.

This module contains SQLModel classes corresponding to the OpenAPI specification
components for type-safe API operations.
"""

from datetime import datetime
from enum import Enum
from typing import ClassVar, Final
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator
from sqlmodel import SQLModel

from syntara.core.constants import FieldLimits
from syntara.forms.models.form_fields import FormDefinition


class FormPromptStatus(str, Enum):
    """Form prompt status enumeration."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


TERMINAL_PROMPT_STATUSES: Final[frozenset[FormPromptStatus]] = frozenset(
    {
        FormPromptStatus.SUBMITTED,
        FormPromptStatus.EXPIRED,
        FormPromptStatus.CANCELLED,
    }
)


class ResponderUserSummary(SQLModel):
    """Summary of a user authorized to respond to a form prompt.

    Similar to UserReference but represents a responder rather than the person
    who actually responded. Used in API responses to show who can respond.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="User's unique identifier")
    username: str = Field(..., description="User's username")


class ResponderGroupSummary(SQLModel):
    """Summary of a group whose members are authorized to respond to a form prompt.

    Represents a group of users who can collectively respond to a prompt.
    Used in API responses to show which groups have response authority.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="Group's unique identifier")
    name: str = Field(..., description="Group's name")


# Status transition guard

_ALLOWED_TRANSITIONS: Final[dict[FormPromptStatus, frozenset[FormPromptStatus]]] = {
    FormPromptStatus.PENDING: frozenset(
        {
            FormPromptStatus.SUBMITTED,
            FormPromptStatus.EXPIRED,
            FormPromptStatus.CANCELLED,
        }
    ),
    FormPromptStatus.SUBMITTED: frozenset(),
    FormPromptStatus.EXPIRED: frozenset(),
    FormPromptStatus.CANCELLED: frozenset(),
}


def can_transition(current: FormPromptStatus, target: FormPromptStatus) -> bool:
    """Return whether ``current`` may legally move to ``target``."""
    return target in _ALLOWED_TRANSITIONS[current]


class FormPromptCreateRequest(SQLModel):
    """Request payload for creating a form prompt.

    This is an internal schema used by the Workflows component.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    execution_id: UUID = Field(..., description="Parent workflow execution ID")
    project_id: UUID = Field(..., description="Project ID (denormalized from execution)")
    prompt_node_id: str = Field(..., description="Canvas node ID from the workflow definition")
    name: str = Field(
        ..., min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Display name for the form prompt"
    )
    message: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Resolved message shown above the form",
    )
    loop_iteration_path: list[int] = Field(
        default_factory=list,
        description="Enclosing-loop indices, outermost first (empty when not inside a loop)",
    )
    temporal_activity_id: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Temporal activity ID to signal on submit (defaults to prompt_node_id)",
    )
    timeout_at: datetime | None = Field(None, description="When this prompt expires (null = no timeout)")
    form_definition: FormDefinition = Field(..., description="Form schema defining fields to collect")
    submit_label: str | None = Field(
        default=None, max_length=FieldLimits.FORM_SUBMIT_LABEL_MAX_LENGTH, description="Submit button label"
    )
    success_message: str | None = Field(
        default=None, max_length=FieldLimits.FORM_SUCCESS_MESSAGE_MAX_LENGTH, description="Success message after submit"
    )
    timezone: str | None = Field(
        default=None, max_length=FieldLimits.FORM_TIMEZONE_MAX_LENGTH, description="IANA timezone for date fields"
    )
    css_override: str | None = Field(
        default=None, max_length=FieldLimits.FORM_CSS_OVERRIDE_MAX_LENGTH, description="Custom CSS for form rendering"
    )
    # FK validation: UUIDs must exist in users/groups tables (enforced at service layer)
    responder_user_ids: list[UUID] | None = Field(
        None,
        max_length=FieldLimits.APPROVER_LIST_MAX_LENGTH,
        description="User IDs who can respond (null = any user with form_prompt:submit permission)",
    )
    responder_group_ids: list[UUID] | None = Field(
        None,
        max_length=FieldLimits.APPROVER_LIST_MAX_LENGTH,
        description="Group IDs whose members can respond",
    )

    @field_validator("loop_iteration_path")
    @classmethod
    def _non_negative_loop_iteration_path(cls, value: list[int]) -> list[int]:
        if any(index < 0 for index in value):
            msg = "loop_iteration_path entries must be non-negative integers"
            raise ValueError(msg)
        return value


class BatchFormPromptStatus(str, Enum):
    """Status values that can be submitted in batch form prompt updates.

    This is a system-actionable subset of FormPromptStatus.
    """

    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BatchFormPromptUpdate(SQLModel):
    """Single update within a batch form prompt request."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    prompt_id: UUID = Field(..., description="ID of the form prompt")
    status: BatchFormPromptStatus = Field(..., description="Status to set")
    notes: str | None = Field(
        None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description="Optional notes explaining the status change",
    )


class BatchFormPromptRequest(SQLModel):
    """Request payload for batch updating form prompt statuses."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    updates: list[BatchFormPromptUpdate] = Field(
        ..., min_length=1, max_length=100, description="List of form prompt status updates to apply"
    )


class FormPromptSummary(SQLModel):
    """Minimal form prompt response for internal workflow engine endpoints.

    Contains only the 8 documented fields used by expire/cancel activities
    and workflow lifecycle management. Does not expose user-submitted form data
    or rendering configuration fields (those will appear in FormPromptRead for
    user-facing endpoints in AAP-91889).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="Form prompt unique identifier")
    execution_id: UUID = Field(..., description="Parent workflow execution ID")
    project_id: UUID = Field(..., description="Project ID (denormalized from execution)")
    prompt_node_id: str = Field(..., description="Canvas node ID from the workflow definition")
    name: str = Field(..., description="Display name for the form prompt")
    status: FormPromptStatus = Field(..., description="Current prompt status")
    loop_iteration_path: list[int] = Field(default_factory=list, description="Enclosing-loop indices, outermost first")
    temporal_activity_id: str | None = Field(None, description="Temporal activity ID for async completion")


class BatchUpdateResult(SQLModel):
    """Single result within a batch update response."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    prompt_id: str = Field(..., description="ID of the form prompt")
    success: bool = Field(..., description="Whether the update succeeded")
    message: str | None = Field(None, description="Success message if applicable")
    error: str | None = Field(None, description="Error message if update failed")


class BatchUpdateResponse(SQLModel):
    """Response payload for batch form prompt updates."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    results: list[BatchUpdateResult] = Field(..., description="Individual update results")
    total_success: int = Field(..., ge=0, description="Count of successful updates")
    total_failed: int = Field(..., ge=0, description="Count of failed updates")
