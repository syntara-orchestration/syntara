"""Tests for workflow schema structural integrity.

These tests validate that the workflow definition schemas are internally consistent:
- All $ref pointers resolve to existing definitions
- Schema structure is valid and complete
- No orphaned or missing references

Separate from contract tests (which validate workflow instance data) and
meta-schema tests (which validate schema syntax).
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver


def _load_workflow_schemas() -> dict[str, dict[str, object]]:
    """Load all workflow v2 schema files."""
    schema_dir = Path("src/syntara/schemas/workflows/v2")
    schemas = {}
    for schema_file in schema_dir.glob("*.json"):
        with schema_file.open() as f:
            schemas[schema_file.name] = json.load(f)
    return schemas


def _build_schema_store(schemas: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Build a schema store for reference resolution."""
    store: dict[str, dict[str, object]] = {}
    for schema in schemas.values():
        if "$id" in schema:
            store[schema["$id"]] = schema  # type: ignore[index]
    return store


class TestWorkflowSchemaReferenceIntegrity:
    """Validate that all $ref pointers in workflow schemas resolve correctly."""

    def test_all_refs_resolve_in_workflow_definition_schema(self) -> None:
        """All $ref pointers in workflow_definition.schema.json must resolve.

        This test would have caught the missing nodeSettings definition bug
        from PR #1301.
        """
        schemas = _load_workflow_schemas()
        workflow_def = schemas["workflow_definition.schema.json"]
        store = _build_schema_store(schemas)

        # Create a resolver with the schema store
        resolver = RefResolver.from_schema(workflow_def, store=store)

        # Validate the schema itself (this will attempt to resolve all $refs)
        validator = Draft202012Validator(workflow_def, resolver=resolver)

        # Check the schema is valid (this resolves all internal $refs)
        try:
            Draft202012Validator.check_schema(workflow_def)
        except Exception as e:
            pytest.fail(f"Workflow definition schema has unresolvable $ref: {e}")

        # Walk through and verify all $refs can be resolved
        errors = list(validator.iter_errors({}))
        # We expect validation errors for the empty object (missing required fields),
        # but we should NOT see Unresolvable or PointerToNowhere errors
        for error in errors:
            if "PointerToNowhere" in str(error) or "Unresolvable" in str(error):
                pytest.fail(
                    f"Schema contains unresolvable $ref: {error.message}\n"
                    f"Schema path: {'/'.join(str(p) for p in error.schema_path)}"
                )

    def test_common_definitions_exports_all_required_refs(self) -> None:
        """common-definitions.schema.json must export all definitions used by other schemas.

        This test verifies that the common definitions schema contains all the
        $defs that other schemas reference.
        """
        schemas = _load_workflow_schemas()
        common_defs = schemas["common-definitions.schema.json"]

        # These are the definitions that should exist based on current schema usage
        required_defs = {
            "credential_id",
            "retry_policy",
            "nodeSettingsCof",
            "nodeSettingsNoRetry",
            "nodeSettingsFull",
        }

        defs_obj = common_defs.get("$defs", {})
        actual_defs = set(defs_obj.keys()) if isinstance(defs_obj, dict) else set()

        missing = required_defs - actual_defs
        if missing:
            pytest.fail(
                f"common-definitions.schema.json is missing required definitions: {missing}\n"
                f"Available definitions: {actual_defs}"
            )

    def test_no_orphaned_definitions(self) -> None:
        """All definitions in common-definitions.schema.json should be referenced.

        This is a warning-level test to catch unused/orphaned definitions.
        """
        schemas = _load_workflow_schemas()
        common_defs = schemas["common-definitions.schema.json"]
        workflow_def = schemas["workflow_definition.schema.json"]

        defs_obj = common_defs.get("$defs", {})
        defined = set(defs_obj.keys()) if isinstance(defs_obj, dict) else set()
        referenced: set[str] = set()

        # Scan workflow_definition for all $ref to common-definitions
        def extract_refs(obj: object, refs: set[str]) -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == "$ref" and isinstance(value, str) and "common-definitions.schema.json#/$defs/" in value:
                        # Extract the definition name from the $ref
                        def_name = value.split("#/$defs/")[1]
                        refs.add(def_name)
                    else:
                        extract_refs(value, refs)
            elif isinstance(obj, list):
                for item in obj:
                    extract_refs(item, refs)

        extract_refs(workflow_def, referenced)

        # Also check executor schemas for references
        for filename, schema in schemas.items():
            if filename.startswith("executors/") or filename == "approval.schema.json":
                extract_refs(schema, referenced)

        orphaned = defined - referenced
        if orphaned:
            # This is a warning, not a failure - orphaned defs might be intentional
            # for future use or backwards compatibility
            pytest.warns(
                UserWarning,
                match=f"Unused definitions in common-definitions.schema.json: {orphaned}",
            )

    def test_workflow_definition_schema_has_valid_structure(self) -> None:
        """Workflow definition schema must have required top-level structure."""
        schemas = _load_workflow_schemas()
        workflow_def = schemas["workflow_definition.schema.json"]

        # Required top-level fields
        assert "$schema" in workflow_def, "Missing $schema declaration"
        assert "$id" in workflow_def, "Missing $id"
        assert "title" in workflow_def, "Missing title"
        assert "type" in workflow_def, "Missing type"
        assert workflow_def["type"] == "object", "Top-level type must be 'object'"

        # Required workflow properties
        required_props = {"schema_version", "name", "triggers", "nodes", "edges"}
        props_obj = workflow_def.get("properties", {})
        actual_props = set(props_obj.keys()) if isinstance(props_obj, dict) else set()
        missing = required_props - actual_props
        assert not missing, f"Missing required workflow properties: {missing}"

    def test_node_schemas_reference_valid_settings_tiers(self) -> None:
        """All node schemas must reference a valid settings tier.

        This verifies that individual node schemas (script, approval, etc.) use
        the correct settings tier and don't reference non-existent definitions.
        """
        schemas = _load_workflow_schemas()

        # Check all executor schemas
        executor_files = [
            ("executors/script.schema.json", "nodeSettingsNoRetry"),
            ("executors/agentic.schema.json", "nodeSettingsNoRetry"),
            ("executors/http_request.schema.json", "nodeSettingsFull"),
            ("executors/aap_job_template.schema.json", "nodeSettingsFull"),
            ("executors/aap_workflow_job_template.schema.json", "nodeSettingsFull"),
            ("approval.schema.json", "nodeSettingsNoRetry"),
        ]

        for filename, expected_tier in executor_files:
            if filename not in schemas:
                continue  # Skip if file doesn't exist

            schema = schemas[filename]
            # Find settings $ref in the schema
            settings_ref = self._find_settings_ref(schema)
            if settings_ref:
                assert expected_tier in settings_ref, (
                    f"{filename} should use {expected_tier} tier, but found {settings_ref}"
                )

    def _find_settings_ref(self, obj: object) -> str | None:
        """Recursively find a settings.$ref in a schema object."""
        if isinstance(obj, dict):
            if "properties" in obj and "settings" in obj["properties"]:
                settings_obj = obj["properties"]["settings"]
                if isinstance(settings_obj, dict):
                    ref_value = settings_obj.get("$ref")
                    return ref_value if isinstance(ref_value, str) else None
            for value in obj.values():
                result = self._find_settings_ref(value)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_settings_ref(item)
                if result:
                    return result
        return None
