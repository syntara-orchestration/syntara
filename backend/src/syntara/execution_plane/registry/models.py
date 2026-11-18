"""Database records for installed Execution Plane plugin step types."""

from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.base.base_resource import AuditLevel


class ExecutionPlanePlugin(BaseResource, table=True):
    """Managed Action manifest and workload image used for EP dispatch."""

    __tablename__ = "execution_plane_plugins"
    __table_args__ = (
        UniqueConstraint("name", name="uq_execution_plane_plugins_name"),
        UniqueConstraint("step_identity", name="uq_execution_plane_plugins_step_identity"),
    )
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Action name declared by the plugin manifest",
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
