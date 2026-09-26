"""Cluster persistence model and lifecycle states."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, Relationship, SQLModel

from execution_plane.models.constants import EP_SCHEMA

if TYPE_CHECKING:
    type ExecutionTarget = Any


class ClusterStatus(StrEnum):
    """Lifecycle states of a cluster."""

    REGISTERING = "registering"
    ACTIVE = "active"
    DRAINING = "draining"
    ERROR = "error"


class Cluster(SQLModel, table=True):
    """A registered control-plane cluster."""

    __tablename__ = "clusters"
    __table_args__ = (UniqueConstraint("endpoint", name="clusters_endpoint_key"), {"schema": EP_SCHEMA})

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False, unique=True))
    endpoint: str = Field(sa_column=Column(String, nullable=False))
    status: ClusterStatus = Field(
        default=ClusterStatus.REGISTERING,
        sa_column=Column(
            SAEnum(
                ClusterStatus, native_enum=False, values_callable=lambda members: [member.value for member in members]
            ),
            nullable=False,
        ),
    )
    enabled: bool = Field(default=True, nullable=False)
    status_message: str | None = Field(default=None, nullable=True)
    api_key: str = Field(sa_column=Column(String, nullable=False), repr=False, exclude=True)
    labels: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    created_by: uuid.UUID = Field(nullable=False)
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_by: uuid.UUID = Field(nullable=False)
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    execution_targets: list["ExecutionTarget"] = Relationship(back_populates="cluster")
