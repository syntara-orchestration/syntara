"""Group SQLModel for role-based access control.

This module provides the Group model for organizing users into groups,
the UserGroup association table for the many-to-many relationship,
and API request/response schemas following SQLModel Pattern 1.
Groups are included in JWT tokens as the ``groups`` claim.
"""

from enum import StrEnum
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, String, Table
from sqlmodel import Field, Index, SQLModel, text

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.base.soft_deletable import SoftDeletableResource
from syntara.core.models.pagination import ResourcesResponse


class GroupSource(StrEnum):
    """Source of group creation."""

    LOCAL = "local"
    IDP = "idp"


# Many-to-many association table between users and groups
user_groups = Table(
    "user_groups",
    BaseResource.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

# Tracks which groups an IdP auto-assigned to a user (for scoped sync on login)
user_idp_groups = Table(
    "user_idp_groups",
    BaseResource.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("identity_provider_id", ForeignKey("identity_providers.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)


class Group(SoftDeletableResource, table=True):
    """Group model for organizing users.

    Groups provide a way to organize users for access control and are
    included in the JWT ``groups`` claim as a flat list of group names.

    Attributes:
        id: Primary key UUID (from BaseResource)
        created_at: Timestamp of group creation (from BaseResource)
        updated_at: Timestamp of last update (from BaseResource)
        labels: Optional key-value metadata (from BaseResource)
        deleted_at: Soft delete timestamp (from SoftDeletableResource)
        deleted_by: UUID of user who performed soft delete (from SoftDeletableResource)
        name: Unique group name (e.g., "engineering", "admins")
        description: Optional description of the group's purpose
        created_by: UUID of user who created this group

    """

    __tablename__ = "groups"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier for the resource",
        index=True,
    )

    # Filterable fields for API list endpoints
    __filterable_fields__: ClassVar[list[str]] = [
        "id",
        "created_at",
        "updated_at",
        "name",
        "description",
        "created_by",
        "created_by_name",
        "source",
    ]

    # Sortable fields for API list endpoints
    __sortable_fields__: ClassVar[list[str]] = [
        "created_at",
        "updated_at",
        "name",
    ]

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Unique group name",
        index=True,
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        sa_type=String(FieldLimits.DESCRIPTION_MAX_LENGTH),  # type: ignore[call-overload]
        description="Description of the group's purpose",
    )

    created_by: UUID | None = Field(
        default=None,
        foreign_key="users.id",
        description="User who created this group",
    )

    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in system group",
        index=True,
    )

    source: str = Field(
        default=GroupSource.LOCAL,
        sa_type=String(10),  # type: ignore[call-overload]
        description="Source of group creation (local or idp)",
        index=True,
    )

    # Partial unique index for name (only for non-deleted groups)
    __table_args__ = (
        Index(
            "ix_groups_name_unique",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of Group."""
        return f"<Group(id={self.id}, name={self.name})>"


# ============================================================================
# API Request/Response Schemas (Pattern 1: Separate models with table=False)
# ============================================================================


class GroupCreate(SQLModel):
    """Schema for creating a new group (POST /groups)."""

    name: str = Field(..., min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Group name")
    description: str | None = Field(
        None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH, description="Group description"
    )


class GroupUpdate(SQLModel):
    """Schema for updating a group (PATCH /groups/{id}).

    All fields are optional for partial updates.
    """

    name: str | None = Field(
        None, min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Update group name"
    )
    description: str | None = Field(
        None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH, description="Update group description"
    )


class GroupRead(BaseResource):
    """Schema for group response (GET /groups/{id}).

    Includes all fields from the database table model.
    """

    name: str
    description: str | None = None
    is_builtin: bool = False
    created_by: UUID | None = None
    source: str = GroupSource.LOCAL
    member_count: int = 0


class MembershipSource(SQLModel):
    """Describes how a user got membership in a group."""

    type: str = Field(description="Source type: 'manual' or 'idp'")
    provider_name: str | None = Field(default=None, description="IdP name if source is 'idp'")
    provider_id: UUID | None = Field(default=None, description="IdP ID if source is 'idp'")


class UserGroupRead(GroupRead):
    """Group response with membership source info for a specific user."""

    membership_sources: list[MembershipSource] = Field(
        default_factory=list, description="How this user was assigned to this group"
    )


# ============================================================================
# List Response
# ============================================================================


class GroupListResponse(ResourcesResponse[GroupRead]):
    """Paginated list response for groups."""


class UserGroupListResponse(ResourcesResponse[UserGroupRead]):
    """Paginated list response for user groups."""


class GroupListParams(BaseListParams):
    """Query parameters for listing groups."""


# ============================================================================
# Membership Schemas
# ============================================================================


class GroupMemberAdd(SQLModel):
    """Schema for adding a member to a group (POST /groups/{id}/members)."""

    user_id: UUID = Field(..., description="UUID of the user to add to the group")


class GroupMemberAddResponse(SQLModel):
    """Response schema for adding a member to a group."""

    message: str = Field(default="Member added successfully", description="Confirmation message")


class UserGroupsSet(SQLModel):
    """Schema for declaratively setting a user's group memberships (PUT /users/{id}/groups).

    The provided list replaces all current memberships. An empty list removes
    the user from all groups.
    """

    group_ids: list[UUID] = Field(
        default_factory=list, description="Complete list of group IDs the user should belong to"
    )
