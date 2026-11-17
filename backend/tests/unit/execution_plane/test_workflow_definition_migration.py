"""Workflow definition migration to Execution Plane credential bindings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest

from syntara.execution_plane.database.migrations import (
    WorkflowCredentialMigrationError,
    _downgrade_workflow_definition,
    _migrate_workflow_definition,
)
from syntara.execution_plane.database.models import MigrationWorkflowDefinition
from syntara.execution_plane.registry.stub import StubPluginRegistry
from tests.fixtures.execution_plane import echo_plugin_registry


def _definition(node_type: str = "script", credential_id: str | None = None) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "code": "printf 'hello'",
        "environment": {"EXAMPLE": "value"},
    }
    if credential_id is not None:
        parameters["credential_id"] = credential_id
    return {
        "id": "workflow",
        "name": "Workflow",
        "nodes": [{"id": "node", "type": node_type, "parameters": parameters}],
        "edges": [],
    }


def test_migration_models_validate_stored_definition_shape() -> None:
    definition = _definition()
    definition["nodes"][0]["custom_field"] = "value"

    model = MigrationWorkflowDefinition.model_validate(definition)

    assert model.nodes[0].type == "script"
    assert model.nodes[0].model_dump()["custom_field"] == "value"


def test_script_migration_removes_temporary_legacy_credential_without_bindings() -> None:
    definition = _definition(credential_id=str(uuid4()))

    migrated = _migrate_workflow_definition(definition, frozenset({"script"}), StubPluginRegistry())

    parameters = migrated["nodes"][0]["parameters"]
    assert isinstance(parameters, dict)
    assert "credential_id" not in parameters
    assert "credential_bindings" not in parameters


def test_recipe_capable_node_migrates_legacy_credential_to_all_registry_recipes() -> None:
    credential_id = str(uuid4())
    definition = _definition(node_type="echo", credential_id=credential_id)

    migrated = _migrate_workflow_definition(definition, frozenset({"echo"}), echo_plugin_registry())

    parameters = migrated["nodes"][0]["parameters"]
    assert isinstance(parameters, dict)
    assert parameters["credential_bindings"] == [
        {"credential_recipe_id": "acme.echo.api-token", "credential_ref": credential_id},
        {"credential_recipe_id": "acme.echo.workspace-token", "credential_ref": credential_id},
    ]
    assert "credential_id" not in parameters


def test_migration_is_idempotent_and_preserves_unrelated_fields() -> None:
    definition = _definition(node_type="echo", credential_id=str(uuid4()))
    definition["labels"] = {"environment": "test"}
    definition["nodes"][0]["name"] = "Echo"
    first = _migrate_workflow_definition(definition, frozenset({"echo"}), echo_plugin_registry())
    first["labels"]["extra"] = "value"

    second = _migrate_workflow_definition(first, frozenset({"echo"}), echo_plugin_registry())

    assert second == first
    assert second["labels"] == {"environment": "test", "extra": "value"}


def test_definition_without_legacy_credential_is_unchanged() -> None:
    definition = _definition()
    original = deepcopy(definition)

    migrated = _migrate_workflow_definition(definition, frozenset({"script"}), StubPluginRegistry())

    assert migrated == original


def test_unsupported_node_type_is_unchanged() -> None:
    definition = _definition(node_type="http_request", credential_id=str(uuid4()))
    original = deepcopy(definition)

    migrated = _migrate_workflow_definition(definition, frozenset({"script"}), StubPluginRegistry())

    assert migrated == original


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        ([{"id": "node", "type": "echo"}], "Field required"),
        ([{"id": "node", "type": "echo", "parameters": None}], "valid dictionary or instance"),
        ([{"id": "node", "type": "echo", "parameters": {"credential_id": "not-a-uuid"}}], "valid UUID"),
        (
            [
                {
                    "id": "node",
                    "type": "echo",
                    "parameters": {
                        "credential_id": str(uuid4()),
                        "credential_bindings": [
                            {"credential_recipe_id": "acme.echo.api-token", "credential_ref": str(uuid4())}
                        ],
                    },
                }
            ],
            "cannot combine",
        ),
    ],
)
def test_invalid_definitions_fail_closed(nodes: list[object], message: str) -> None:
    definition = {"id": "workflow", "name": "Workflow", "nodes": nodes, "edges": []}

    with pytest.raises(WorkflowCredentialMigrationError, match=message):
        _migrate_workflow_definition(definition, frozenset({"echo"}), echo_plugin_registry())


def test_registry_exception_is_wrapped() -> None:
    class BrokenRegistry:
        def credential_recipe_ids(self, node_type: str) -> tuple[str, ...]:
            message = "registry unavailable"
            raise RuntimeError(message)

    definition = _definition(node_type="echo", credential_id=str(uuid4()))

    with pytest.raises(WorkflowCredentialMigrationError, match="registry unavailable"):
        _migrate_workflow_definition(definition, frozenset({"echo"}), BrokenRegistry())


def test_downgrade_uses_first_binding_and_warns_for_multiple_bindings(caplog: pytest.LogCaptureFixture) -> None:
    first_credential_id = str(uuid4())
    second_credential_id = str(uuid4())
    definition = _definition(node_type="echo")
    definition["nodes"][0]["parameters"]["credential_bindings"] = [
        {"credential_recipe_id": "acme.echo.api-token", "credential_ref": first_credential_id},
        {"credential_recipe_id": "acme.echo.workspace-token", "credential_ref": second_credential_id},
    ]

    with caplog.at_level("WARNING", logger="syntara.execution_plane.database.migrations"):
        downgraded = _downgrade_workflow_definition(definition, frozenset({"echo"}))

    parameters = downgraded["nodes"][0]["parameters"]
    assert isinstance(parameters, dict)
    assert parameters["credential_id"] == first_credential_id
    assert "credential_bindings" not in parameters
    assert "uses the first credential binding" in caplog.text


def test_downgrade_is_noop_for_script_nodes_without_bindings() -> None:
    definition = _definition()
    original = deepcopy(definition)

    downgraded = _downgrade_workflow_definition(definition, frozenset({"script"}))

    assert downgraded == original


def test_invalid_node_type_fails_validation() -> None:
    definition = {
        "schema_version": "2.0.0",
        "name": "Workflow",
        "triggers": [],
        "nodes": [{"id": "node", "type": 123, "parameters": {}}],
        "edges": [],
    }

    with pytest.raises(WorkflowCredentialMigrationError, match="Input should be a valid string"):
        _migrate_workflow_definition(definition, frozenset({"script"}), StubPluginRegistry())
