"""SQLModel utility functions for database model configuration.

This module provides helper functions for common SQLModel/SQLAlchemy patterns
used throughout the Nexus project.
"""

import json
from enum import Enum
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import Column, TypeDecorator
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.elements import TextClause

from syntara.core.exceptions import SafeValueError


def postgres_enum_column(
    enum_type: type[Enum],
    postgres_name: str,
    *,
    nullable: bool = False,
    index: bool = False,
    create_constraint: bool = False,
    server_default: TextClause | None = None,
) -> Column[Any]:
    """Create a SQLAlchemy Column for PostgreSQL enum types.

    This helper creates a properly configured Column that references
    existing PostgreSQL enum types created by Alembic migrations.

    The function uses create_type=False to prevent SQLAlchemy from attempting
    to create the enum type, as it should already exist from migrations.

    Args:
        enum_type: Python Enum class (e.g., ProviderStatus, ToolStatus)
        postgres_name: PostgreSQL enum type name as defined in migrations
            (e.g., "tool_provider_status", "tool_status")
        nullable: Whether column allows NULL values (default: False)
        index: Whether to create an index on this column (default: False)
        create_constraint: Whether to create a CHECK constraint for enum values
            at the database level (default: False)
        server_default: Server-side default value (default: None)

    Returns:
        Configured Column for use with SQLModel Field's sa_column parameter

    Example:
        >>> from enum import Enum
        >>> class ProviderStatus(str, Enum):
        ...     AVAILABLE = "available"
        ...     ERROR = "error"
        ...     VALIDATING = "validating"
        >>>
        >>> status: ProviderStatus = Field(
        ...     default=ProviderStatus.VALIDATING,
        ...     sa_column=postgres_enum_column(
        ...         ProviderStatus,
        ...         "tool_provider_status",
        ...         index=True,
        ...     ),
        ...     description="Current status of the provider",
        ... )
        >>>
        >>> # With CHECK constraint for additional database-level validation
        >>> role: UserRole = Field(
        ...     sa_column=postgres_enum_column(
        ...         UserRole,
        ...         "userrole",
        ...         index=True,
        ...         create_constraint=True,
        ...     ),
        ...     description="User role for access control",
        ... )

    Note:
        This pattern is used to ensure that SQLModel/SQLAlchemy references
        the correct PostgreSQL enum type name that was created by Alembic
        migrations, avoiding type mismatch errors like:
        "type 'providerstatus' does not exist"

    """
    return Column(
        SAEnum(
            enum_type,
            name=postgres_name,
            create_type=False,  # Use existing enum from migration
            create_constraint=create_constraint,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=nullable,
        index=index,
        server_default=server_default,
    )


class DiscriminatedJSONB(TypeDecorator):  # type: ignore[type-arg]
    """Simplified SQLAlchemy type for discriminated unions stored as JSONB.

    This type leverages Pydantic's TypeAdapter to handle discriminated unions
    automatically, eliminating the need for custom factory functions.

    Example:
        >>> from typing import Union, Literal
        >>> from typing_extensions import Annotated
        >>> from pydantic import Field
        >>> from sqlmodel import SQLModel

        >>> class MCPConfig(SQLModel):
        ...     provider_type: Literal['mcp'] = 'mcp'
        ...     api_key: str

        >>> class MockConfig(SQLModel):
        ...     provider_type: Literal['mock'] = 'mock'
        ...     endpoint: str

        >>> ConfigUnion = Annotated[
        ...     Union[MCPConfig, MockConfig],
        ...     Field(discriminator='provider_type')
        ... ]

        >>> configuration: ConfigUnion = Field(
        ...     sa_type=DiscriminatedJSONB(ConfigUnion),
        ...     discriminator="provider_type"
        ... )

    """

    impl = JSONB
    cache_ok = True

    def __init__(self, union_type: type, *args: object, **kwargs: object) -> None:
        """Initialize with a discriminated union type.

        Args:
            union_type: The discriminated union type (e.g., Annotated[Union[...], Field(discriminator=...)])
            args: Additional positional arguments for parent class
            kwargs: Additional keyword arguments for parent class

        """
        super().__init__(*args, **kwargs)
        self.type_adapter: TypeAdapter[Any] = TypeAdapter(union_type)

    def process_bind_param(self, value: object, _dialect: Dialect) -> object:
        """Convert SQLModel instance to dict for database storage."""
        if value is None:
            return None

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value

        # Fallback serialization
        try:
            return json.loads(json.dumps(value))
        except (TypeError, ValueError) as e:
            type_name = type(value).__name__
            error_msg = f"Cannot serialize value of type '{type_name}' to JSON"
            raise SafeValueError(error_msg) from e

    def process_result_value(self, value: object, _dialect: Dialect) -> object:
        """Convert dict from database back to appropriate discriminated type."""
        if value is None or not isinstance(value, dict):
            return value

        try:
            return self.type_adapter.validate_python(value)
        except (TypeError, ValueError):
            # If validation fails, return raw dict
            return value
