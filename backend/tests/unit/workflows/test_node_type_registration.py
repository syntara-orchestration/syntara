"""Cross-surface parity tests for node type registration.

Ensures that all node types are properly registered across all seven surfaces:
1. NodeType enum
2. JSON Schema file
3. node_type_catalog.json entry
4. workflow_definition.schema.json branch
5. _NODE_SETTINGS_CLASS binding
6. NODE_OUTPUT_MODELS entry
7. _AllNodeTypes union
"""

import json
from typing import Any, cast

import pytest

from syntara.schemas import SCHEMA_DIR
from syntara.workflows.models.workflow_definition import WorkflowDefinition
from syntara.workflows.workflow_engine.graph import _NODE_SETTINGS_CLASS
from syntara.workflows.workflow_engine.models.workflow_definition import NODE_OUTPUT_MODELS, NodeType


@pytest.fixture
def catalog() -> dict[str, Any]:
    """Load node_type_catalog.json."""
    catalog_path = SCHEMA_DIR / "workflows" / "v2" / "catalog" / "node_type_catalog.json"
    return cast("dict[str, Any]", json.loads(catalog_path.read_text()))


@pytest.fixture
def workflow_def_schema() -> dict[str, Any]:
    """Load workflow_definition.schema.json."""
    schema_path = SCHEMA_DIR / "workflows" / "v2" / "workflow_definition.schema.json"
    return cast("dict[str, Any]", json.loads(schema_path.read_text()))


@pytest.fixture
def executor_control_types() -> set[str]:
    """All executor and control node types (excludes triggers and internal_activity)."""
    return {
        NodeType.SCRIPT,
        NodeType.HTTP_REQUEST,
        NodeType.AAP_JOB_TEMPLATE,
        NodeType.AAP_WORKFLOW_JOB_TEMPLATE,
        NodeType.AGENTIC,
        NodeType.APPROVAL,
        NodeType.FORM_PROMPT,
        # INTERNAL_ACTIVITY excluded - internal implementation detail, not user-facing
        NodeType.CONDITION,
        NodeType.SWITCH,
        NodeType.CONVERGE,
        NodeType.LOOP,
        NodeType.WAIT,
    }


class TestNodeTypeCatalogParity:
    """Every executor/control NodeType appears in node_type_catalog.json."""

    def test_all_executor_control_types_in_catalog(
        self, catalog: dict[str, Any], executor_control_types: set[str]
    ) -> None:
        """All executor/control NodeType values have a catalog entry."""
        catalog_types = {entry["type"] for entry in catalog["node_types"]}
        missing = executor_control_types - catalog_types
        assert not missing, f"NodeType values missing from catalog: {missing}"

    def test_catalog_schema_refs_exist(self, catalog: dict[str, Any]) -> None:
        """All schema_ref paths in the catalog resolve to existing files."""
        base_dir = SCHEMA_DIR / "workflows" / "v2"
        for entry in catalog["node_types"]:
            schema_ref = entry["schema_ref"]
            # schema_ref is relative to the catalog directory (e.g., "../executors/script.schema.json")
            schema_path = (base_dir / "catalog" / schema_ref).resolve()
            assert schema_path.exists(), f"Schema file not found: {schema_ref} (resolved to {schema_path})"

    def test_catalog_entries_have_parameter_schema(self, catalog: dict[str, Any]) -> None:
        """All catalog entries point to schemas with a parameterSchema."""
        base_dir = SCHEMA_DIR / "workflows" / "v2"
        for entry in catalog["node_types"]:
            schema_ref = entry["schema_ref"]
            schema_path = (base_dir / "catalog" / schema_ref).resolve()
            schema = json.loads(schema_path.read_text())
            assert "parameterSchema" in schema, f"{schema_ref} missing parameterSchema"


class TestWorkflowDefinitionSchemaParity:
    """Every executor/control NodeType has a branch in workflow_definition.schema.json."""

    def test_all_types_have_definition_branch(
        self, workflow_def_schema: dict[str, Any], executor_control_types: set[str]
    ) -> None:
        """All executor/control types have a const branch in $defs.node."""
        node_branches = workflow_def_schema["$defs"]["node"]["oneOf"]
        schema_types = set()
        for branch in node_branches:
            # Each branch is allOf[{$ref: node_base}, {properties: {type: {const: "..."}}}]
            for item in branch.get("allOf", []):
                props = item.get("properties", {})
                type_def = props.get("type", {})
                if "const" in type_def:
                    schema_types.add(type_def["const"])

        missing = executor_control_types - schema_types
        assert not missing, f"NodeType values missing from workflow_definition.schema.json: {missing}"


class TestNodeSettingsClassParity:
    """Every non-trigger NodeType has a _NODE_SETTINGS_CLASS entry."""

    def test_all_non_trigger_types_have_settings_class(self, executor_control_types: set[str]) -> None:
        """All executor/control types are in _NODE_SETTINGS_CLASS."""
        settings_types = set(_NODE_SETTINGS_CLASS.keys())
        missing = executor_control_types - settings_types
        assert not missing, f"NodeType values missing from _NODE_SETTINGS_CLASS: {missing}"


class TestNodeOutputModelsParity:
    """Every executor/control NodeType has a NODE_OUTPUT_MODELS entry."""

    def test_all_types_have_output_model(self, executor_control_types: set[str]) -> None:
        """All executor/control types are in NODE_OUTPUT_MODELS."""
        output_types = set(NODE_OUTPUT_MODELS.keys())
        missing = executor_control_types - output_types
        assert not missing, f"NodeType values missing from NODE_OUTPUT_MODELS: {missing}"


class TestTypedNodeUnionParity:
    """Every executor/control type can be parsed through WorkflowDefinition."""

    def test_form_prompt_in_union(self) -> None:
        """form_prompt type parses through the discriminated union."""
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "t", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "n",
                        "type": "form_prompt",
                        "parameters": {"input_schema": {"type": "object"}},
                    }
                ],
                "edges": [],
            }
        )
        assert wf.nodes[0].type == "form_prompt"

    @pytest.mark.parametrize(
        ("node_type", "params"),
        [
            ("script", {"language": "bash", "code": "echo 1"}),
            ("http_request", {"method": "GET", "url": "https://example.com"}),
            ("approval", {}),
            ("condition", {"condition": "1 == 1"}),
        ],
    )
    def test_sample_types_parse(self, node_type: str, params: dict[str, Any]) -> None:
        """Sample of other types parse correctly (spot check)."""
        wf = WorkflowDefinition.model_validate(
            {
                "schema_version": "2.0.0",
                "name": "test",
                "triggers": [{"id": "t", "type": "manual_trigger", "parameters": {}}],
                "nodes": [{"id": "n", "type": node_type, "parameters": params}],
                "edges": [],
            }
        )
        assert wf.nodes[0].type == node_type
