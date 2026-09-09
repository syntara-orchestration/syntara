"""API request/response models for form endpoints.

This module contains SQLModel classes corresponding to the OpenAPI specification
components for type-safe API operations.
"""

from enum import Enum
from typing import ClassVar, Final
from uuid import UUID

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


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
