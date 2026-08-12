"""Credential SQLModel definition for database storage.

A named instance of a credential type. Contains metadata (name, description,
labels) and a secret_id FK pointing to the secrets routing table. Encrypted
field values are stored separately in encrypted_secrets via SecretService.
"""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import Field, Relationship, SQLModel

from syntara.core.models.base.base_resource import AuditLevel
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.user_owned import UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference
from syntara.credentials.models.credential_type import CredentialType


class Credential(NamedResource, UserOwnedResource, table=True):
    """Credential database model.

    Extends NamedResource and UserOwnedResource with credential-specific fields.
    Encrypted field values are stored in the encrypted_secrets table
    via the secret_id FK → secrets routing table.
    """

    __tablename__ = "credentials"

    credential_type_id: UUID = Field(
        foreign_key="credential_types.id",
        description="ID of the credential type schema",
        index=True,
    )

    secret_id: UUID | None = Field(
        default=None,
        foreign_key="secrets.id",
        description="FK to secret routing record containing encrypted inputs",
        index=True,
    )

    enabled: bool = Field(
        default=True,
        description="Whether this credential is active",
    )

    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project namespace for resource isolation",
        index=True,
    )

    credential_type: CredentialType | None = Relationship()

    __table_args__ = (
        Index("ix_credentials_name_project_unique", "name", "project_id", unique=True),
        Index("ix_credentials_created_at_id", "created_at", "id"),
    )

    __filterable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__filterable_fields__,
                *UserOwnedResource.__filterable_fields__,
                "credential_type_id",
                "secret_id",
                "enabled",
                "project_id",
            ]
        )
    )

    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__sortable_fields__,
                *UserOwnedResource.__sortable_fields__,
            ]
        )
    )

    # Audit trail: metadata only (no secret_id to prevent exposure in audit logs)
    __auditable__: ClassVar[AuditLevel] = AuditLevel.META
    __auditable_fields__: ClassVar[list[str]] = [
        "name",
        "description",
        "credential_type_id",
        "enabled",
        "project_id",
        "created_by",
        "updated_by",
    ]


class CredentialCreate(SQLModel):
    """Schema for creating a new credential."""

    name: str = Field(min_length=1, max_length=255, description="Human-readable credential name")
    description: str | None = Field(default=None, max_length=2000, description="Optional description")
    credential_type_id: UUID = Field(description="ID of the credential type")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Field values validated against type schema")
    labels: dict[str, str] = Field(default_factory=dict, description="Key-value labels")
    project_id: UUID = Field(description="Project to assign credential to")


class CredentialRead(NamedResource, UserOwnedResource):
    """Schema for credential API responses. Secret fields masked as $encrypted$."""

    created_by: UserReference | UUID | str | None = Field(default=None, description="User who created the credential")  # type: ignore[assignment]
    updated_by: UserReference | UUID | str | None = Field(
        default=None, description="User who last modified the credential"
    )  # type: ignore[assignment]

    _USER_REF_SCHEMA: ClassVar[dict[str, Any]] = {
        "readOnly": True,
        "anyOf": [
            {"$ref": "#/components/schemas/UserReference"},
            {"type": "null"},
        ],
    }

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
        "created_by": _USER_REF_SCHEMA,
        "updated_by": _USER_REF_SCHEMA,
    }

    credential_type_id: UUID
    inputs: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    project_id: UUID
    workflow_count: int = Field(default=0, description="Number of workflows referencing this credential")
    integration_count: int = Field(default=0, description="Number of integrations using this credential")


class ProjectCredentialCreate(SQLModel):
    """Schema for creating a credential via a project-scoped endpoint (project_id from URL path)."""

    name: str = Field(min_length=1, max_length=255, description="Human-readable credential name")
    description: str | None = Field(default=None, max_length=2000, description="Optional description")
    credential_type_id: UUID = Field(description="ID of the credential type")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Field values validated against type schema")
    labels: dict[str, str] = Field(default_factory=dict, description="Key-value labels")


class CredentialUpdate(SQLModel):
    """Schema for partially updating a credential. $encrypted$ preserves existing values."""

    project_id: UUID | None = Field(
        default=None, description="Project ID (immutable after creation; rejected if different from stored value)"
    )
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    inputs: dict[str, Any] | None = None
    enabled: bool | None = None
    labels: dict[str, str] | None = None


class CredentialListResponse(ResourcesResponse[CredentialRead]):
    """Paginated list response for credentials."""


class CredentialWorkflowRef(SQLModel):
    """Reference to a workflow that uses a credential."""

    id: UUID
    name: str
    description: str | None = None
    created_by: str | UUID | None = Field(default=None, description="Username or UUID of the workflow creator")
    node_names: list[str] = Field(default_factory=list, description="Names of nodes using this credential")
    last_execution_at: datetime | None = Field(default=None, description="Timestamp of the most recent execution")
    last_execution_status: str | None = Field(default=None, description="Status of the most recent execution")


class CredentialWorkflowListResponse(ResourcesResponse[CredentialWorkflowRef]):
    """Paginated list response for credential workflow references."""
