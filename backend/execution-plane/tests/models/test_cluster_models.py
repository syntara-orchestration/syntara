"""Persistence-model contracts for clusters and execution targets."""

from __future__ import annotations

import uuid

from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.constants import EP_SCHEMA
from execution_plane.models.execution_target import BackendType, ExecutionTarget, TargetStatus
from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlmodel import SQLModel


def test_cluster_table_exposes_required_lifecycle_and_audit_contract() -> None:
    """Removing cluster lifecycle, credential, or audit storage breaks registration."""
    table = Cluster.__table__  # type: ignore[attr-defined]

    assert table.name == "clusters"
    assert table.schema == EP_SCHEMA
    assert set(ClusterStatus) == {
        ClusterStatus.REGISTERING,
        ClusterStatus.ACTIVE,
        ClusterStatus.DRAINING,
        ClusterStatus.ERROR,
    }
    assert any(
        constraint.name == "clusters_endpoint_key" and {column.name for column in constraint.columns} == {"endpoint"}
        for constraint in table.constraints
    )
    assert table.c.api_key.nullable is False
    assert table.c.labels.type.__class__.__name__ == "JSONB"
    assert isinstance(table.c.api_key.type, String)
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True
    assert {"created_by", "created_at", "updated_by", "updated_at"} <= set(table.c.keys())
    assert isinstance(table.c.status.type, SAEnum)
    assert table.c.status.type.native_enum is False
    assert repr(Cluster(endpoint="https://cluster.example", api_key="secret"))
    assert "secret" not in repr(Cluster(endpoint="https://cluster.example", api_key="secret"))
    assert "api_key" not in Cluster(endpoint="https://cluster.example", api_key="secret").model_dump()


def test_execution_target_belongs_to_cluster_with_default_and_draining_state() -> None:
    """Removing target ownership/default fields would permit invalid cluster registrations."""
    table = ExecutionTarget.__table__  # type: ignore[attr-defined]

    assert table.name == "execution_targets"
    assert table.schema == EP_SCHEMA
    assert table.c.cluster_id.nullable is False
    assert table.constraints
    assert any(
        constraint.name == "execution_targets_cluster_name_key"
        and {column.name for column in constraint.columns} == {"cluster_id", "name"}
        for constraint in table.constraints
    )
    default_index = next(index for index in table.indexes if index.name == "uq_execution_targets_default_cluster")
    assert default_index.unique is True
    assert next(iter(table.c.cluster_id.foreign_keys)).target_fullname == "execution_plane.clusters.id"
    assert table.c.is_default.default.arg is False
    assert TargetStatus.DRAINING.value == "draining"
    assert table.c.api_key.nullable is False
    assert isinstance(table.c.api_key.type, String)
    assert table.c.updated_at.type.timezone is True
    assert {"created_by", "created_at", "updated_by", "updated_at"} <= set(table.c.keys())
    assert "secret" not in repr(
        ExecutionTarget(
            cluster_id=uuid.uuid4(),
            name="default",
            backend_type=BackendType.VANILLA_K8S,
            endpoint="https://target.example",
            api_key="secret",
        )
    )
    assert (
        "api_key"
        not in ExecutionTarget(
            cluster_id=uuid.uuid4(),
            name="default",
            backend_type=BackendType.VANILLA_K8S,
            endpoint="https://target.example",
            api_key="secret",
        ).model_dump()
    )
    assert ExecutionTarget.__mapper__.relationships["cluster"].mapper.class_ is Cluster  # type: ignore[attr-defined]
    assert Cluster.__mapper__.relationships["execution_targets"].mapper.class_ is ExecutionTarget  # type: ignore[attr-defined]


def test_models_package_registers_cluster_and_target_tables_with_sqlmodel_metadata() -> None:
    """Alembic autogeneration requires both persistence tables in model metadata."""
    assert SQLModel.metadata.tables["execution_plane.clusters"] is Cluster.__table__  # type: ignore[attr-defined]
    assert SQLModel.metadata.tables["execution_plane.execution_targets"] is ExecutionTarget.__table__  # type: ignore[attr-defined]
