"""User API request/response schemas.

This module provides schemas for user management endpoints following the
SQLModel Pattern 1 (separate models with table=False), consistent with
the Group model pattern.
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict, EmailStr, SecretStr, field_validator
from sqlmodel import Field, SQLModel

from syntara.auth.passwords import validate_password_complexity
from syntara.core.constants import FieldLimits
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.group import MembershipSource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user import AuthType


class UserCreate(SQLModel):
    """Schema for creating a new local user (POST /users).

    Excludes auto-generated fields: id, created_at, updated_at, last_login, preferences.
    """

    username: str = Field(..., min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Unique username")
    email: EmailStr | None = Field(default=None, max_length=FieldLimits.NAME_MAX_LENGTH, description="Email address")
    first_name: str | None = Field(
        default=None, max_length=FieldLimits.NAME_MAX_LENGTH, description="User's first name"
    )
    last_name: str | None = Field(default=None, max_length=FieldLimits.NAME_MAX_LENGTH, description="User's last name")
    password: SecretStr = Field(..., min_length=14, description="Plaintext password (will be hashed)")
    is_enabled: bool = Field(default=True, description="Whether the user account is enabled")
    group_names: list[str] | None = Field(
        default=None,
        description=(
            "Groups to assign the user to. "
            "Omit to use the default (users group). "
            "Pass an empty list to skip group assignment."
        ),
    )

    @field_validator("password")
    @classmethod
    def check_password_complexity(cls, v: SecretStr) -> SecretStr:
        """Enforce InfoSec password complexity requirements."""
        validate_password_complexity(v.get_secret_value())
        return v


class UserUpdate(SQLModel):
    """Schema for updating a user (PATCH /users/{id}).

    All fields are optional for partial updates.
    """

    username: str | None = Field(
        None, min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Update username"
    )
    first_name: str | None = Field(
        None, min_length=1, max_length=FieldLimits.NAME_MAX_LENGTH, description="Update first name"
    )
    last_name: str | None = Field(None, max_length=FieldLimits.NAME_MAX_LENGTH, description="Update last name")
    email: EmailStr | None = Field(None, max_length=FieldLimits.NAME_MAX_LENGTH, description="Update email address")
    password: SecretStr | None = Field(
        None, min_length=14, description="New password (will be hashed). Omit to keep current password."
    )
    is_enabled: bool | None = Field(None, description="Enable or disable user account")

    @field_validator("password")
    @classmethod
    def check_password_complexity(cls, v: SecretStr | None) -> SecretStr | None:
        """Enforce InfoSec password complexity requirements when password is provided."""
        if v is not None:
            validate_password_complexity(v.get_secret_value())
        return v


class UserRead(SQLModel):
    """Schema for user response (GET /users/{id}).

    Includes all user fields except sensitive data (password_hash, preferences).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    username: str
    email: str | None = None
    first_name: str
    last_name: str | None = None
    is_enabled: bool
    is_builtin: bool = False
    auth_type: AuthType = AuthType.LOCAL
    auth_sources: list[str] = []
    last_login: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GroupMemberRead(UserRead):
    """User response with membership source info for a specific group."""

    membership_sources: list[MembershipSource] = Field(
        default_factory=list, description="How this user was assigned to this group"
    )


# ============================================================================
# List Response
# ============================================================================


class UserListResponse(ResourcesResponse[UserRead]):
    """Paginated list response for users."""


class GroupMemberListResponse(ResourcesResponse[GroupMemberRead]):
    """Paginated list response for group members."""


class UserListParams(BaseListParams):
    """Query parameters for listing users."""

    username: str | None = Field(default=None, description="Filter by username")
    first_name: str | None = Field(default=None, description="Filter by first name")
    last_name: str | None = Field(default=None, description="Filter by last name")
    auth_type: AuthType | None = Field(default=None, description="Filter by authentication type (local or federated)")
    auth_source: str | None = Field(default=None, description="Filter by authentication source")
