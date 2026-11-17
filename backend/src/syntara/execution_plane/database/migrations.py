"""Database migrations for stored Execution Plane workflow definitions."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from pydantic import ValidationError

from syntara.execution_plane.database.models import (
    MigrationCredentialBinding,
    MigrationWorkflowDefinition,
    MigrationWorkflowNode,
)
from syntara.execution_plane.registry.stub import PluginRegistry, StubPluginRegistry
from syntara.execution_plane.utils import execution_plane_supported_node_types

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence

    from sqlalchemy.engine import Connection

    WorkflowDefinitionTransform = Callable[[dict[str, Any], Collection[str]], dict[str, Any]]


logger = logging.getLogger(__name__)


class WorkflowCredentialMigrationError(Exception):
    """Raised when a workflow definition cannot be migrated safely."""


def migrate_workflow_credential_bindings(
    connection: Connection,
    *,
    node_types: Sequence[str] | None = None,
    registry: PluginRegistry | None = None,
) -> None:
    """Migrate stored workflow definitions on the supplied database connection."""
    resolved_node_types = execution_plane_supported_node_types() if node_types is None else node_types
    resolved_registry = registry if registry is not None else StubPluginRegistry()
    _update_workflow_definitions(
        connection,
        resolved_node_types,
        lambda definition, types: _migrate_workflow_definition(definition, types, resolved_registry),
    )


def _migrate_workflow_definition(
    definition: dict[str, Any],
    node_types: Collection[str],
    registry: PluginRegistry,
) -> dict[str, Any]:
    """Migrate legacy node credentials into Execution Plane bindings.

    Node types without credential recipes have their temporary legacy credential field removed.
    Recipe-capable node types create one binding per reachable recipe using the legacy reference.
    """
    migrated = _validated_definition(definition)

    for node in migrated.nodes:
        _migrate_node(node, node_types, registry)

    return _dump_definition(migrated)


def _migrate_node(node: MigrationWorkflowNode, node_types: Collection[str], registry: PluginRegistry) -> None:
    """Migrate one workflow node when its type is targeted."""
    if node.type not in node_types:
        return
    parameters = node.parameters
    if parameters.credential_id is None and parameters.credential_bindings is None:
        return
    if parameters.credential_id is not None and parameters.credential_bindings is not None:
        message = f"Node {node.id!r} cannot combine legacy and binding credentials"
        raise WorkflowCredentialMigrationError(message)

    credential_id = parameters.credential_id
    parameters.credential_id = None
    if credential_id is None:
        return
    recipe_ids = _credential_recipe_ids(registry, node.type)
    if recipe_ids:
        parameters.credential_bindings = [
            MigrationCredentialBinding(credential_recipe_id=recipe_id, credential_ref=credential_id)
            for recipe_id in recipe_ids
        ]


def downgrade_workflow_credential_bindings(
    connection: Connection,
    *,
    node_types: Sequence[str] | None = None,
) -> None:
    """Restore legacy credential fields from the first binding on the supplied connection."""
    resolved_node_types = execution_plane_supported_node_types() if node_types is None else node_types
    _update_workflow_definitions(connection, resolved_node_types, _downgrade_workflow_definition)


def _downgrade_workflow_definition(definition: dict[str, Any], node_types: Collection[str]) -> dict[str, Any]:
    """Restore the first binding's credential reference as the legacy field."""
    downgraded = _validated_definition(definition)

    for node in downgraded.nodes:
        _downgrade_node(node, node_types)

    return _dump_definition(downgraded)


def _downgrade_node(node: MigrationWorkflowNode, node_types: Collection[str]) -> None:
    """Restore one workflow node's first binding as its legacy credential."""
    if node.type not in node_types:
        return
    parameters = node.parameters
    if parameters.credential_bindings is None:
        return
    if parameters.credential_id is not None:
        message = f"Node {node.id!r} cannot combine legacy and binding credentials"
        raise WorkflowCredentialMigrationError(message)

    bindings = parameters.credential_bindings
    parameters.credential_bindings = None
    if not bindings:
        return
    if len(bindings) > 1:
        logger.warning(
            "Node %s has %d credential bindings; downgrade uses the first credential binding",
            node.id,
            len(bindings),
        )
    parameters.credential_id = bindings[0].credential_ref


def _validated_definition(definition: dict[str, Any]) -> MigrationWorkflowDefinition:
    """Validate stored JSON before mutating it."""
    try:
        return MigrationWorkflowDefinition.model_validate(definition)
    except ValidationError as error:
        message = f"Invalid workflow definition: {error}"
        raise WorkflowCredentialMigrationError(message) from error


def _dump_definition(definition: MigrationWorkflowDefinition) -> dict[str, Any]:
    """Serialize a migration model while omitting absent credential fields."""
    dumped = definition.model_dump(mode="json")
    for node in dumped["nodes"]:
        parameters = node["parameters"]
        if parameters["credential_id"] is None:
            del parameters["credential_id"]
        if parameters["credential_bindings"] is None:
            del parameters["credential_bindings"]
    return dumped


def _update_workflow_definitions(
    connection: Connection,
    node_types: Collection[str],
    transform: WorkflowDefinitionTransform,
) -> None:
    """Apply a definition transformation to changed workflow versions in batches."""
    row_batches = (
        connection.execute(sa.text("SELECT id, workflow_definition FROM workflow_versions ORDER BY id"))
        .mappings()
        .partitions(100)
    )

    for row_batch in row_batches:
        for row in row_batch:
            definition = row["workflow_definition"]
            if not isinstance(definition, dict):
                message = f"Workflow version {row['id']} definition must contain an object"
                raise WorkflowCredentialMigrationError(message)
            transformed = transform(definition, node_types)
            if transformed == definition:
                continue
            connection.execute(
                sa.text("UPDATE workflow_versions SET workflow_definition = CAST(:definition AS jsonb) WHERE id = :id"),
                parameters={"definition": json.dumps(transformed), "id": row["id"]},
            )


def _credential_recipe_ids(registry: PluginRegistry, node_type: str) -> Sequence[str]:
    """Resolve recipes and convert registry failures into migration failures."""
    try:
        return registry.credential_recipe_ids(node_type)
    except Exception as error:
        message = f"Credential recipe registry failed for node type {node_type!r}: {error}"
        raise WorkflowCredentialMigrationError(message) from error
