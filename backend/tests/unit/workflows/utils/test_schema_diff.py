"""Tests for SubWorkflow output schema breaking changes detection."""

from typing import Any

from syntara.workflows.utils.schema_diff import (
    detect_output_schema_breaking_changes,
    detect_output_schema_changes,
    detect_workflow_breaking_changes,
    detect_workflow_contract_changes,
)


class TestDetectOutputSchemaBreakingChanges:
    """Test breaking change detection for individual output schemas."""

    def test_no_breaking_changes_when_old_schema_is_none(self) -> None:
        """First publish has no breaking changes."""
        new_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
            },
        }
        changes = detect_output_schema_breaking_changes(None, new_schema)
        assert len(changes) == 0

    def test_contract_diff_reports_optional_addition_without_marking_breaking(self) -> None:
        old_schema = {"type": "object", "properties": {"status": {"type": "string"}}}
        new_schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}, "details": {"type": "object"}},
        }

        changes = detect_output_schema_changes(old_schema, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "added_output"
        assert changes[0].field_path == "details"
        assert changes[0].is_breaking is False
        assert detect_output_schema_breaking_changes(old_schema, new_schema) == []

    def test_contract_diff_includes_new_required_output_on_first_declaration_as_nonbreaking(self) -> None:
        new_schema = {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        }

        changes = detect_output_schema_changes(None, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "new_required_output"
        assert changes[0].is_breaking is False

    def test_removed_output_detected(self) -> None:
        """Detect when an output field is removed."""
        old_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
            },
        }
        new_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
            },
        }
        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "removed_output"
        assert changes[0].field_path == "build_id"
        assert changes[0].old_type == "number"

    def test_type_change_detected(self) -> None:
        """Detect when a field's type changes."""
        old_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
            },
        }
        new_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "object"},
            },
        }
        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "type_change"
        assert changes[0].field_path == "artifact_url"
        assert changes[0].old_type == "string"
        assert changes[0].new_type == "object"

    def test_new_required_output_detected(self) -> None:
        """Detect when a new required field is added."""
        old_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
            },
        }
        new_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
                "deployment_id": {"type": "string"},
            },
            "required": ["deployment_id"],
        }
        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "new_required_output"
        assert changes[0].field_path == "deployment_id"
        assert changes[0].new_type == "string"

    def test_new_optional_field_not_breaking(self) -> None:
        """New optional fields are not breaking changes."""
        old_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
            },
        }
        new_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
                "optional_field": {"type": "string"},
            },
        }
        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        # New optional fields are not breaking
        assert len(changes) == 0

    def test_existing_optional_output_became_required(self) -> None:
        """Strengthening an existing optional field to required is breaking."""
        old_schema = {
            "type": "object",
            "properties": {"deployment_id": {"type": "string"}},
        }
        new_schema = {
            "type": "object",
            "properties": {"deployment_id": {"type": "string"}},
            "required": ["deployment_id"],
        }

        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "required_output"
        assert changes[0].field_path == "deployment_id"

    def test_nested_field_removed(self) -> None:
        """Detect when a nested field is removed."""
        old_schema = {
            "type": "object",
            "properties": {
                "result": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "code": {"type": "number"},
                    },
                },
            },
        }
        new_schema = {
            "type": "object",
            "properties": {
                "result": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                    },
                },
            },
        }
        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert len(changes) == 1
        assert changes[0].change_type == "removed_output"
        assert changes[0].field_path == "result.code"

    def test_nested_type_change_detected_without_explicit_parent_type(self) -> None:
        """Object properties are compared even when their schema omits ``type: object``."""
        old_schema = {
            "type": "object",
            "properties": {"metadata": {"properties": {"status": {"type": "string"}}}},
        }
        new_schema = {
            "type": "object",
            "properties": {"metadata": {"properties": {"status": {"type": "number"}}}},
        }

        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert any(change.change_type == "type_change" and change.field_path == "metadata.status" for change in changes)

    def test_multiple_breaking_changes(self) -> None:
        """Detect multiple breaking changes at once."""
        old_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
                "deployment_id": {"type": "string"},
            },
        }
        new_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "object"},  # Type change
                "deployment_id": {"type": "string"},
                "new_field": {"type": "string"},
            },
            "required": ["new_field"],  # New required
        }
        changes = detect_output_schema_breaking_changes(old_schema, new_schema)

        assert len(changes) == 3
        change_types = {c.change_type for c in changes}
        assert "removed_output" in change_types  # build_id removed
        assert "type_change" in change_types  # artifact_url changed
        assert "new_required_output" in change_types  # new_field required

    def test_all_outputs_removed_when_new_schema_is_none(self) -> None:
        """When new schema is None, all old outputs are removed."""
        old_schema = {
            "type": "object",
            "properties": {
                "artifact_url": {"type": "string"},
                "build_id": {"type": "number"},
            },
        }
        changes = detect_output_schema_breaking_changes(old_schema, None)

        assert len(changes) == 2
        assert all(c.change_type == "removed_output" for c in changes)
        field_paths = {c.field_path for c in changes}
        assert field_paths == {"artifact_url", "build_id"}


class TestDetectWorkflowBreakingChanges:
    """Test breaking change detection for entire workflow definitions."""

    def test_contract_changes_include_nonbreaking_output_additions(self) -> None:
        old_definition: dict[str, Any] = {
            "triggers": [
                {
                    "id": "child-trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {"output_schema": {"type": "object", "properties": {}}},
                }
            ]
        }
        new_definition: dict[str, Any] = {
            "triggers": [
                {
                    "id": "child-trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {"output_schema": {"type": "object", "properties": {"status": {"type": "string"}}}},
                }
            ]
        }

        contract_changes = detect_workflow_contract_changes(old_definition, new_definition)
        breaking_changes = detect_workflow_breaking_changes(old_definition, new_definition)

        assert contract_changes["child-trigger"][0]["change_type"] == "added_output"
        assert contract_changes["child-trigger"][0]["is_breaking"] is False
        assert breaking_changes == {}

    def test_no_breaking_changes_for_first_publish(self) -> None:
        """First publish has no breaking changes."""
        new_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {"artifact_url": {"type": "string"}},
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        changes = detect_workflow_breaking_changes(None, new_definition)
        assert len(changes) == 0

    def test_breaking_changes_detected_for_subworkflow_trigger(self) -> None:
        """Breaking changes detected for SubWorkflow Trigger."""
        old_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                                "build_id": {"type": "number"},
                            },
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        new_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "subworkflow_trigger",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "artifact_url": {"type": "string"},
                            },
                        },
                    },
                }
            ],
            "nodes": [],
            "edges": [],
        }

        changes = detect_workflow_breaking_changes(old_definition, new_definition)

        assert len(changes) == 1
        assert "subworkflow_trigger" in changes
        assert len(changes["subworkflow_trigger"]) == 1
        assert changes["subworkflow_trigger"][0]["change_type"] == "removed_output"

    def test_non_subworkflow_triggers_ignored(self) -> None:
        """Non-SubWorkflow triggers are not checked."""
        old_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "manual_trigger",
                    "type": "manual_trigger",
                    "parameters": {},
                }
            ],
            "nodes": [],
            "edges": [],
        }

        new_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "manual_trigger",
                    "type": "manual_trigger",
                    "parameters": {},
                }
            ],
            "nodes": [],
            "edges": [],
        }

        changes = detect_workflow_breaking_changes(old_definition, new_definition)
        assert len(changes) == 0

    def test_multiple_triggers_with_breaking_changes(self) -> None:
        """Breaking changes detected across multiple triggers."""
        old_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "trigger1",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {"field1": {"type": "string"}},
                        },
                    },
                },
                {
                    "id": "trigger2",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {"field2": {"type": "number"}},
                        },
                    },
                },
            ],
            "nodes": [],
            "edges": [],
        }

        new_definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "triggers": [
                {
                    "id": "trigger1",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {},  # field1 removed
                        },
                    },
                },
                {
                    "id": "trigger2",
                    "type": "subworkflow_trigger",
                    "parameters": {
                        "output_schema": {
                            "type": "object",
                            "properties": {"field2": {"type": "string"}},  # Type changed
                        },
                    },
                },
            ],
            "nodes": [],
            "edges": [],
        }

        changes = detect_workflow_breaking_changes(old_definition, new_definition)

        assert len(changes) == 2
        assert "trigger1" in changes
        assert "trigger2" in changes
