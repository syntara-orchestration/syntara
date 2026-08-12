"""UserOwnedResource SQLModel definition.

This module contains the UserOwnedResource SQLModel class that extends BaseResource
with user ownership and modification tracking.
"""

from abc import ABC
from typing import Any, ClassVar
from uuid import UUID

from sqlmodel import Field

from syntara.core.models.base import BaseResource


class UserOwnedResource(BaseResource, ABC):
    """Abstract SQLModel for resources tracking ownership and modifications.

    Extends BaseResource with fields to track which users created and last
    updated the resource, enabling audit trails and access control.

    This class cannot be instantiated directly and does not create database tables.
    Concrete subclasses must inherit from this class and set table=True.

    Attributes:
        created_by: UUID of user who created the resource (required)
        updated_by: Optional UUID of user who last updated the resource

    Inherits from BaseResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        labels: Optional key-value metadata

    """

    # User ownership tracking
    created_by: UUID = Field(
        foreign_key="principals.id",
        description="User (or automation) that created the resource",
        index=True,
    )

    updated_by: UUID | None = Field(
        default=None,
        foreign_key="principals.id",
        description="User (or automation) that last updated the resource",
        index=True,
    )

    def update_by_user(self, user_id: UUID) -> None:
        """Update the resource's updated_by field.

        Args:
            user_id: UUID of the user performing the update

        """
        self.updated_by = user_id

    def is_owned_by(self, user_id: UUID) -> bool:
        """Check if the resource is owned by the specified user.

        Args:
            user_id: UUID of the user to check ownership for

        Returns:
            True if the resource was created by the specified user

        """
        return self.created_by == user_id

    def was_updated_by(self, user_id: UUID) -> bool:
        """Check if the resource was last updated by the specified user.

        Args:
            user_id: UUID of the user to check for last update

        Returns:
            True if the resource was last updated by the specified user

        """
        return self.updated_by == user_id

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **BaseResource.FIELD_SCHEMA_EXTRAS,
        "created_by": {"readOnly": True, "example": "770e8400-e29b-41d4-a716-446655440000"},
        "updated_by": {"readOnly": True, "example": "880e8400-e29b-41d4-a716-446655440000"},
    }

    # User ownership fields extend base fields
    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "created_by",
        "updated_by",
    ]

    # User ownership sortable fields extend base fields (not typically sorted by users)
    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
    ]
