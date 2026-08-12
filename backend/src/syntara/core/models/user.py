"""User SQLModel for authentication and authorization.

This module provides the User model that combines BaseResource and SoftDeletableResource
for managing platform users with authentication and authorization.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, ClassVar
from uuid import UUID, uuid4

from pydantic import StringConstraints
from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, DateTime, Field, Index

from syntara.core.constants import FieldLimits
from syntara.core.models.base import SoftDeletableResource
from syntara.core.models.principal import PrincipalType


class AuthType(StrEnum):
    """Authentication type for users."""

    LOCAL = "local"
    FEDERATED = "federated"


class User(SoftDeletableResource, table=True):
    """User model representing platform users.

    Extends SoftDeletableResource (which includes BaseResource) with user-specific
    authentication and profile fields.

    Attributes:
        id: Primary key UUID (from BaseResource)
        created_at: Timestamp of user creation (from BaseResource)
        updated_at: Timestamp of last update (from BaseResource)
        labels: Optional key-value metadata (from BaseResource)
        deleted_at: Soft delete timestamp (from SoftDeletableResource)
        deleted_by: UUID of user who performed soft delete (from SoftDeletableResource)
        username: Unique username for authentication
        email: Email address
        first_name: User's first name
        last_name: User's last name
        password_hash: Argon2id hash for local auth (null for federated-only users)
        is_enabled: Whether the user account is enabled
        last_login: Timestamp of last successful login
        preferences: JSON field for user preferences and settings

    """

    __tablename__ = "users"
    __principal_type__: ClassVar[PrincipalType] = PrincipalType.USER

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        foreign_key="principals.id",
        description="Unique identifier for the resource",
        index=True,
    )

    # Filterable fields for API list endpoints
    __filterable_fields__: ClassVar[list[str]] = [
        "id",
        "created_at",
        "updated_at",
        "username",
        "email",
        "first_name",
        "last_name",
        "is_enabled",
        "auth_type",
    ]

    # Sortable fields for API list endpoints
    __sortable_fields__: ClassVar[list[str]] = [
        "created_at",
        "updated_at",
        "username",
        "email",
        "first_name",
        "last_name",
        "last_login",
        "auth_type",
    ]

    # Required fields
    username: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Unique username for authentication",
        index=True,
    )

    email: Annotated[str, StringConstraints(to_lower=True)] | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Email address",
        index=True,
    )

    first_name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="User's first name",
    )

    last_name: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="User's last name",
    )

    @property
    def display_name(self) -> str:
        """Computed display name from first and last name."""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    password_hash: str | None = Field(
        default=None,
        exclude=True,
        sa_type=String(255),  # type: ignore[call-overload]
        description="Argon2id password hash for local authentication (null for federated users)",
    )

    auth_type: AuthType = Field(
        default=AuthType.LOCAL,
        sa_type=String(10),  # type: ignore[call-overload]
        description="Authentication type: 'local' (password) or 'federated' (identity provider). Mutually exclusive.",
        index=True,
        sa_column_kwargs={"server_default": text("'local'")},
    )

    # Optional fields with defaults
    is_enabled: bool = Field(
        default=True,
        description="Whether the user account is enabled",
        index=True,
        sa_column_kwargs={"server_default": text("true")},
    )

    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in system user",
        index=True,
        sa_column_kwargs={"server_default": text("false")},
    )

    last_login: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp of last successful login",
    )

    preferences: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSON,
        description="User preferences and settings as JSON",
    )

    authz_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"server_default": text("'{}'::jsonb")},
        description="User metadata for authorization conditions",
    )

    token_version: int = Field(
        default=0,
        sa_column_kwargs={"server_default": text("0")},
    )

    # Table arguments for partial unique constraints
    __table_args__ = (
        # Partial unique index for username (only for non-deleted users)
        Index(
            "ix_users_username_unique",
            "username",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_users_email_unique",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL AND deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of User.

        Returns:
            String representation

        """
        return f"<User(id={self.id}, username={self.username})>"

    def update_last_login(self) -> None:
        """Update last_login timestamp to current time."""
        self.last_login = datetime.now(UTC)
