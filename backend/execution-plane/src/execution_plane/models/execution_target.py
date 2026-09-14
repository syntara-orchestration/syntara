from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel

EP_SCHEMA = "execution_plane"


class BackendType(StrEnum):
    VANILLA_K8S = "vanilla_k8s"
    OPENSHELL = "openshell"


class TargetStatus(StrEnum):
    REGISTERING = "registering"
    VALIDATING = "validating"
    BOOTSTRAPPING = "bootstrapping"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"


class ExecutionTarget(SQLModel, table=True):
    """A registered compute environment where worker pods run."""

    __tablename__ = "execution_targets"
    __table_args__ = {"schema": EP_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, unique=True)
    backend_type: BackendType
    endpoint: str
    status: TargetStatus = TargetStatus.REGISTERING
    enabled: bool = True
    labels: dict = Field(default={}, sa_column=Column(JSONB, nullable=False, server_default="{}"))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_ran_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
