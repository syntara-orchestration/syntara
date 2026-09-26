"""Tests for the green-field Cluster and ExecutionTarget migration."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


def test_cluster_migration_is_next_revision_and_defines_cluster_table() -> None:
    """The migration must create the Cluster table and target ownership fields."""
    migration = importlib.import_module(
        "execution_plane.migrations.versions.b7c8d9e0f1a2_add_clusters_and_registry_fields"
    )

    assert migration.revision == "b7c8d9e0f1a2"
    assert migration.down_revision == "9f3e1a2b4c7d"
    assert "clusters" in migration.upgrade.__doc__


def test_cluster_migration_requires_an_empty_target_table_and_adds_target_constraints() -> None:
    """The green-field migration rejects existing targets and adds new invariants."""
    migration = importlib.import_module(
        "execution_plane.migrations.versions.b7c8d9e0f1a2_add_clusters_and_registry_fields"
    )

    source = migration.__loader__.get_source(migration.__name__)  # type: ignore[union-attr]
    assert source is not None
    assert "op.create_table" in source
    assert '"clusters"' in source
    assert '"execution_targets_cluster_id_fkey"' in source
    assert '"uq_execution_targets_default_cluster"' in source
    assert 'postgresql_where=sa.text("is_default = true")' in source
    assert "must be empty" in source


def test_cluster_migration_upgrade_records_required_schema_operations() -> None:
    """The upgrade operation creates ownership and lifecycle fields."""
    migration = importlib.import_module(
        "execution_plane.migrations.versions.b7c8d9e0f1a2_add_clusters_and_registry_fields"
    )

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "create_unique_constraint") as create_unique_constraint,
        patch.object(migration.op, "create_foreign_key") as create_foreign_key,
        patch.object(migration.op, "create_index") as create_index,
        patch.object(migration.op, "get_bind") as get_bind,
    ):
        get_bind.return_value.execute.return_value.first.return_value = None
        migration.upgrade()

    cluster_call = next(call for call in create_table.call_args_list if call.args[0] == "clusters")
    cluster_columns = {column.name: column for column in cluster_call.args[1:] if hasattr(column, "name")}
    assert {"id", "endpoint", "status", "enabled", "status_message", "api_key"} <= set(cluster_columns)

    target_columns = {
        call.args[1].name: call.args[1] for call in add_column.call_args_list if call.args[0] == "execution_targets"
    }
    default_column = target_columns["is_default"]
    assert default_column.nullable is False
    assert default_column.server_default is None

    drop_constraint.assert_called_once_with(
        "execution_targets_name_key", "execution_targets", schema="execution_plane", type_="unique"
    )
    create_unique_constraint.assert_called_once_with(
        "execution_targets_cluster_name_key",
        "execution_targets",
        ["cluster_id", "name"],
        schema="execution_plane",
    )

    create_foreign_key.assert_called_once_with(
        "execution_targets_cluster_id_fkey",
        "execution_targets",
        "clusters",
        ["cluster_id"],
        ["id"],
        source_schema="execution_plane",
        referent_schema="execution_plane",
    )
    create_index.assert_called_once()
    index_args, index_kwargs = create_index.call_args
    assert index_args == ("uq_execution_targets_default_cluster", "execution_targets", ["cluster_id"])
    assert index_kwargs["unique"] is True
    assert index_kwargs["schema"] == "execution_plane"
    assert str(index_kwargs["postgresql_where"]) == "is_default = true"


def test_cluster_migration_rejects_existing_execution_targets() -> None:
    migration = importlib.import_module(
        "execution_plane.migrations.versions.b7c8d9e0f1a2_add_clusters_and_registry_fields"
    )

    with (
        patch.object(migration.op, "get_bind") as get_bind,
        pytest.raises(
            RuntimeError,
            match=r"execution_plane\.execution_targets must be empty for this migration",
        ),
    ):
        get_bind.return_value.execute.return_value.first.return_value = object()
        migration._require_empty_execution_targets()


def test_cluster_migration_rejects_duplicate_target_names_on_downgrade() -> None:
    migration = importlib.import_module(
        "execution_plane.migrations.versions.b7c8d9e0f1a2_add_clusters_and_registry_fields"
    )

    with (
        patch.object(migration.op, "get_bind") as get_bind,
        pytest.raises(
            RuntimeError,
            match=r"execution_plane\.execution_targets contains duplicate names",
        ),
    ):
        get_bind.return_value.execute.return_value.first.return_value = ("primary", 2)
        migration._require_unique_target_names_for_downgrade()
