"""Execution target persistence models and lifecycle states."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Index, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel

EP_SCHEMA = "execution_plane"


class BackendType(StrEnum):
    """Supported execution target backends."""

    VANILLA_K8S = "vanilla_k8s"
    OPENSHELL = "openshell"


class TargetStatus(StrEnum):
    """Lifecycle states of an execution target."""

    REGISTERING = "registering"
    VALIDATING = "validating"
    BOOTSTRAPPING = "bootstrapping"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"


class ExecutionTarget(SQLModel, table=True):
    """A registered compute environment where worker pods run."""

    __tablename__ = "execution_targets"
    __table_args__ = (
        UniqueConstraint("name", name="execution_targets_name_key"),
        Index("ix_execution_targets_name", "name"),
        {"schema": EP_SCHEMA},
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    # The migration stores enum values in VARCHAR columns, not native PG enums.
    backend_type: BackendType = Field(
        sa_column=Column(
            SAEnum(
                BackendType, native_enum=False, values_callable=lambda members: [member.value for member in members]
            ),
            nullable=False,
        ),
    )
    endpoint: str
    # Namespace in which this target provisions ephemeral worker pods.
    namespace: str
    # Non-secret reference describing how the worker obtains Kubernetes credentials.
    credential_ref: dict[str, Any] = Field(
        default={},
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    status: TargetStatus = Field(
        default=TargetStatus.REGISTERING,
        sa_column=Column(
            SAEnum(
                TargetStatus, native_enum=False, values_callable=lambda members: [member.value for member in members]
            ),
            nullable=False,
        ),
    )
    enabled: bool = True
    labels: dict[str, Any] = Field(default={}, sa_column=Column(JSONB, nullable=False, server_default="{}"))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_ran_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
