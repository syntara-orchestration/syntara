"""SoftDeletableResource SQLModel definition.

This module contains the SoftDeletableResource SQLModel class that extends BaseResource
with soft deletion tracking capabilities.
"""

from abc import ABC
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from sqlmodel import DateTime, Field

from syntara.core.models.base import BaseResource


class SoftDeletableResource(BaseResource, ABC):
    """Abstract SQLModel for resources supporting soft deletion tracking.

    Extends BaseResource with fields to track when and by whom a resource
    was soft deleted, enabling data recovery and audit trails.

    This class cannot be instantiated directly and does not create database tables.
    Concrete subclasses must inherit from this class and set table=True.

    Attributes:
        deleted_at: Optional timestamp when resource was soft deleted
        deleted_by: Optional UUID of user who performed the soft delete

    Inherits from BaseResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        labels: Optional key-value metadata

    State Transitions:
        [Active] --soft delete--> [Deleted]
                 deleted_at = now()
                 deleted_by = current_user

        [Deleted] --restore--> [Active]
                  deleted_at = null
                  deleted_by = null

    """

    # Type hint for mypy: subclasses may have an email field
    # This prevents type errors when soft_delete() anonymizes email
    if TYPE_CHECKING:
        email: str | None

    # Soft deletion tracking
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp when resource was soft deleted",
        index=True,
    )

    deleted_by: UUID | None = Field(
        default=None,
        foreign_key="users.id",
        description="User who performed the soft delete",
        index=True,
    )

    def is_deleted(self) -> bool:
        """Check if the resource is soft deleted.

        Returns:
            True if the resource is soft deleted (deleted_at is set)

        """
        return self.deleted_at is not None

    def soft_delete(self, user_id: UUID, deletion_time: datetime | None = None) -> None:
        """Mark the resource as soft deleted.

        For resources with an email field, anonymizes the email to prevent
        email reuse attacks where deleted users' emails could be re-registered
        to intercept password resets and communications.

        Args:
            user_id: UUID of the user performing the deletion
            deletion_time: Optional timestamp, defaults to current time

        """
        if deletion_time is None:
            deletion_time = datetime.now(UTC)

        self.deleted_at = deletion_time
        self.deleted_by = user_id

        # Anonymize email field if present to prevent email reuse attacks
        # This prevents an attacker from registering with a deleted user's email
        # to intercept password resets or sensitive communications
        if hasattr(self, "email") and getattr(self, "email", None) is not None:
            self.email = None

    def restore(self) -> None:
        """Restore a soft deleted resource to active state."""
        self.deleted_at = None
        self.deleted_by = None

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **BaseResource.FIELD_SCHEMA_EXTRAS,
        "deleted_at": {"readOnly": True, "example": "2025-10-09T14:00:00Z"},
        "deleted_by": {"readOnly": True, "example": "660e8400-e29b-41d4-a716-446655440000"},
    }

    # Soft deletion fields extend base fields
    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "deleted_at",
        "deleted_by",
    ]

    # Soft deletion sortable fields extend base fields
    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "deleted_at",
    ]
