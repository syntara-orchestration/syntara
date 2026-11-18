"""Database records for installed Execution Plane plugin step types."""

from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column, ForeignKey
from sqlmodel import Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.base.base_resource import AuditLevel
from syntara.core.utils.sqlmodel import postgres_enum_column
from syntara.workflow_core.models import NodeType


class ExecutionPlanePlugin(BaseResource, table=True):
    """Managed Action manifest and workload image used for EP dispatch."""

    __tablename__ = "execution_plane_plugins"
    __table_args__ = (
        UniqueConstraint("name", name="uq_execution_plane_plugins_name"),
        UniqueConstraint("step_identity", name="uq_execution_plane_plugins_step_identity"),
        UniqueConstraint("node_type", name="uq_execution_plane_plugins_node_type"),
    )
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Action name declared by the plugin manifest",
    )

    node_type: NodeType = Field(
        ...,
        description="AO node type dispatched to this Action",
        sa_column=postgres_enum_column(NodeType, "nodetype", nullable=False),
    )

    step_identity: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Container runtime identity used to invoke this Action",
    )

    manifest: dict[str, Any] = Field(
        sa_type=JSONB,
        description="Canonical Action manifest describing the step contract",
    )

    image_reference: str = Field(
        min_length=1,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Fully qualified workload image reference",
    )


class ExecutionPlaneIntegrationType(BaseResource, table=True):
    """Managed IntegrationType manifest referenced by an Execution Plane Action."""

    __tablename__ = "execution_plane_integration_types"
    __table_args__ = (UniqueConstraint("integration_type_id", name="uq_execution_plane_integration_type_id"),)
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    integration_type_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_column=Column(
            String(FieldLimits.NAME_MAX_LENGTH),
            nullable=False,
            index=True,
        ),
        description="IntegrationType identifier declared by its manifest",
    )

    manifest: dict[str, Any] = Field(
        sa_type=JSONB,
        description="Canonical IntegrationType manifest",
    )


class ExecutionPlaneCredentialRecipe(BaseResource, table=True):
    """Managed CredentialRecipe manifest reachable from an IntegrationType."""

    __tablename__ = "execution_plane_credential_recipes"
    __table_args__ = (UniqueConstraint("credential_recipe_id", name="uq_execution_plane_credential_recipe_id"),)
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    credential_recipe_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_column=Column(
            String(FieldLimits.NAME_MAX_LENGTH),
            nullable=False,
            index=True,
        ),
        description="CredentialRecipe identifier declared by its manifest",
    )

    integration_type_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_column=Column(
            String(FieldLimits.NAME_MAX_LENGTH),
            ForeignKey("execution_plane_integration_types.integration_type_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="IntegrationType that can use this CredentialRecipe",
    )

    manifest: dict[str, Any] = Field(
        sa_type=JSONB,
        description="Canonical CredentialRecipe manifest",
    )
