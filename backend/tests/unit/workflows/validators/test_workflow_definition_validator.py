"""Tests for WorkflowValidator."""

from typing import Any

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationSeverity,
)
from syntara.workflows.validators.workflow_definition import WorkflowValidator, _best_branch_messages


@pytest.fixture
def validator() -> WorkflowValidator:
    """Create a WorkflowValidator instance."""
    return WorkflowValidator()


def _valid_definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "print(1)"}}],
        "edges": [{"from": "t1", "to": "n1"}],
    }


class TestValidWorkflowDefinition:
    """Valid V2 workflow definition passes validation."""

    def test_valid_definition_passes(self, validator: WorkflowValidator) -> None:
        validator.validate_workflow_definition(_valid_definition())

    def test_minimal_valid_definition(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "minimal",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }
        validator.validate_workflow_definition(definition)


class TestMissingSchemaVersion:
    """Missing or wrong schema_version."""

    def test_missing_schema_version_raises(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"triggers": [], "nodes": [], "edges": []}
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition(definition)

    def test_wrong_schema_version_raises(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": "1.0.0", "triggers": [], "nodes": [], "edges": []}
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition(definition)

    def test_none_schema_version_raises(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": None, "triggers": [], "nodes": [], "edges": []}
        with pytest.raises(SafeValueError):
            validator.validate_workflow_definition(definition)


class TestMissingRequiredFields:
    """Missing triggers, nodes, or edges fields."""

    def test_missing_triggers_raises(self, validator: WorkflowValidator) -> None:
        definition = {"schema_version": "2.0.0", "nodes": [], "edges": []}
        with pytest.raises(SafeValueError, match="triggers"):
            validator.validate_workflow_definition(definition)

    def test_missing_nodes_raises(self, validator: WorkflowValidator) -> None:
        definition = {"schema_version": "2.0.0", "triggers": [], "edges": []}
        with pytest.raises(SafeValueError, match="nodes"):
            validator.validate_workflow_definition(definition)

    def test_missing_edges_raises(self, validator: WorkflowValidator) -> None:
        definition = {"schema_version": "2.0.0", "triggers": [], "nodes": []}
        with pytest.raises(SafeValueError, match="edges"):
            validator.validate_workflow_definition(definition)


class TestWorkflowNameValidation:
    """Workflow name validation."""

    def test_valid_name_passes(self, validator: WorkflowValidator) -> None:
        validator.validate_workflow_name("my-workflow")

    def test_empty_name_raises(self, validator: WorkflowValidator) -> None:
        with pytest.raises(SafeValueError, match="cannot be empty"):
            validator.validate_workflow_name("")

    def test_whitespace_only_name_passes(self, validator: WorkflowValidator) -> None:
        """Non-empty string with whitespace is accepted (not stripped)."""
        validator.validate_workflow_name("  ")


class TestEmptyDefinition:
    """Completely empty definition dict."""

    def test_empty_dict_raises_on_schema_version(self, validator: WorkflowValidator) -> None:
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition({})


class TestValidationOrder:
    """Schema version is validated before required fields."""

    def test_bad_version_with_missing_fields_raises_version_error(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": "1.0.0"}
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition(definition)


class TestExtraTopLevelFields:
    """Extra top-level fields are rejected by additionalProperties: false."""

    def test_extra_top_level_fields_rejected(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
            "metadata": {"author": "test"},
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            validator.validate_workflow_definition(definition)

    def test_description_field_accepted(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
            "description": "some workflow",
        }
        validator.validate_workflow_definition(definition)

    def test_null_description_accepted(self, validator: WorkflowValidator) -> None:
        """Null description is valid — minLength only applies to strings in Draft 2020-12."""
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
            "description": None,
        }
        validator.validate_workflow_definition(definition)


class TestSchemaValidation:
    """JSON schema validation catches structural violations."""

    def test_fabricated_node_type_rejected(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "totally_fake_type", "parameters": {}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            validator.validate_workflow_definition(definition)

    def test_node_missing_config_rejected(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script"}],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            validator.validate_workflow_definition(definition)

    def test_invalid_node_id_pattern_rejected(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "123-bad!", "type": "script", "parameters": {"language": "python", "code": "x"}},
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            validator.validate_workflow_definition(definition)

    def test_extra_edge_properties_rejected(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "x"}}],
            "edges": [{"from": "t1", "to": "n1", "color": "red", "weight": 5}],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            validator.validate_workflow_definition(definition)

    def test_empty_triggers_rejected(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [],
            "nodes": [],
            "edges": [],
        }
        with pytest.raises(SafeValueError, match="schema validation failed"):
            validator.validate_workflow_definition(definition)


class TestEdgeReferences:
    """Edges must reference existing triggers or nodes."""

    def test_edge_from_references_nonexistent_node_rejected(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "bad-from",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "1"}}],
            "edges": [{"from": "ghost", "to": "n1"}],
        }
        with pytest.raises(SafeValueError, match="non-existent node 'ghost'"):
            validator.validate_workflow_definition(definition)

    def test_edge_to_references_nonexistent_node_rejected(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "bad-to",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "1"}}],
            "edges": [{"from": "t1", "to": "missing"}],
        }
        with pytest.raises(SafeValueError, match="non-existent node 'missing'"):
            validator.validate_workflow_definition(definition)


class TestCycleDetection:
    """Cycle detection rejects cyclic workflow graphs."""

    def test_simple_cycle_rejected(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "cycle-test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "a", "type": "script", "parameters": {"language": "python", "code": "1"}},
                {"id": "b", "type": "script", "parameters": {"language": "python", "code": "2"}},
                {"id": "c", "type": "script", "parameters": {"language": "python", "code": "3"}},
            ],
            "edges": [
                {"from": "t1", "to": "a"},
                {"from": "a", "to": "b"},
                {"from": "b", "to": "c"},
                {"from": "c", "to": "a"},
            ],
        }
        with pytest.raises(SafeValueError, match="cycle"):
            validator.validate_workflow_definition(definition)

    def test_self_loop_rejected(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "self-loop",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "a", "type": "script", "parameters": {"language": "python", "code": "1"}},
            ],
            "edges": [
                {"from": "t1", "to": "a"},
                {"from": "a", "to": "a"},
            ],
        }
        with pytest.raises(SafeValueError, match="cycle"):
            validator.validate_workflow_definition(definition)

    def test_valid_dag_passes(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "dag",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "a", "type": "script", "parameters": {"language": "python", "code": "1"}},
                {"id": "b", "type": "script", "parameters": {"language": "python", "code": "2"}},
                {"id": "c", "type": "script", "parameters": {"language": "python", "code": "3"}},
            ],
            "edges": [
                {"from": "t1", "to": "a"},
                {"from": "a", "to": "b"},
                {"from": "b", "to": "c"},
            ],
        }
        validator.validate_workflow_definition(definition)

    def test_loop_feedback_edge_allowed(self, validator: WorkflowValidator) -> None:
        """Edges with to_port='iterate' are intentional loop-back edges and must not trigger cycle detection."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "loop-workflow",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "loop_node",
                    "type": "loop",
                    "parameters": {"type": "for_each", "items": "${t1.result.items}"},
                },
                {"id": "body", "type": "script", "parameters": {"language": "python", "code": "1"}},
            ],
            "edges": [
                {"from": "t1", "to": "loop_node"},
                {"from": "loop_node", "to": "body", "from_port": "iterate"},
                {"from": "body", "to": "loop_node", "to_port": "iterate"},
            ],
        }
        validator.validate_workflow_definition(definition)


class TestSchemaVersionVariants:
    """Various schema_version format edge cases."""

    def test_version_2_0_without_patch_raises(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": "2.0", "triggers": [], "nodes": [], "edges": []}
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition(definition)

    def test_version_3_0_0_raises(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": "3.0.0", "triggers": [], "nodes": [], "edges": []}
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition(definition)

    def test_integer_version_raises(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": 2, "triggers": [], "nodes": [], "edges": []}
        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            validator.validate_workflow_definition(definition)


class TestTemplateExpressionValidation:
    """Template expression validation is wired into both validator paths."""

    def test_collect_findings_includes_unresolved_reference_error(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "n1",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print(1)",
                        "environment": {"X": "${ghost.output}"},
                    },
                },
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        assert any("ghost" in f.message for f in result.findings)
        ghost_findings = [f for f in result.findings if "ghost" in f.message]
        assert ghost_findings[0].node_id == "n1"

    def test_validate_raises_on_loop_variable_outside_loop(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "n1",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print(1)",
                        "environment": {"X": "${loop.item}"},
                    },
                },
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        with pytest.raises(SafeValueError, match="loop"):
            validator.validate_workflow_definition(definition)

    def test_collect_findings_includes_loop_scope_error(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "n1",
                    "type": "script",
                    "parameters": {
                        "language": "python",
                        "code": "print(1)",
                        "environment": {"X": "${loop.item}"},
                    },
                },
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        assert any("loop" in f.message for f in result.findings)


class TestCollectFindings:
    """collect_findings() returns structured ValidationResult with individual findings."""

    def test_valid_definition_returns_empty_findings(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(_valid_definition())
        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.findings == []

    def test_orphaned_node_finding(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "orphan",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "1"}},
                {"id": "orphan", "type": "script", "parameters": {"language": "python", "code": "2"}},
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        assert result.error_count == 1
        finding = result.findings[0]
        assert finding.severity == ValidationSeverity.error
        assert finding.category == ValidationCategory.orphaned_node
        assert finding.node_id == "orphan"

    def test_replace_switch_with_condition_orphan_is_soft_finding(self, validator: WorkflowValidator) -> None:
        """After Switch→Condition prune, an unreconnected script is unreachable.

        collect_findings reports orphaned_node errors but does not raise — create/update
        save paths use this result for has_validation_issues (save-with-warnings), not
        a hard 422 WORKFLOW_DEFINITION_INVALID response.
        """
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "after-replace",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "cond1",
                    "type": "condition",
                    "name": "Condition",
                    "parameters": {"condition": "true"},
                },
                {
                    "id": "script1",
                    "type": "script",
                    "name": "Script1",
                    "parameters": {"language": "python", "code": "print(1)"},
                },
                {
                    "id": "script3",
                    "type": "script",
                    "name": "Script3",
                    "parameters": {"language": "python", "code": "print(3)"},
                },
            ],
            "edges": [
                {"from": "trigger_manual", "to": "cond1"},
                {"from": "cond1", "to": "script1", "from_port": "true"},
                # script3 left disconnected after prune (no edge)
            ],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        assert result.error_count >= 1
        orphan = next(f for f in result.findings if f.node_id == "script3")
        assert orphan.category == ValidationCategory.orphaned_node
        assert "unreachable" in orphan.message

    def test_multiple_schema_findings_per_node(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "123_bad_id", "type": "script", "name": "Bad ID", "config": {}}],
            "edges": [{"from": "t1", "to": "123_bad_id"}],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        node_findings = [f for f in result.findings if f.node_id == "123_bad_id"]
        assert len(node_findings) >= 3
        assert all(f.category == ValidationCategory.schema_violation for f in node_findings)

    def test_missing_parameters_includes_nested_required_fields(self, validator: WorkflowValidator) -> None:
        """When parameters is missing, supplementary errors show what it should contain."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "config": {}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        messages = [f.message for f in result.findings if f.node_id == "n1"]
        assert "'parameters' is a required property" in messages
        assert "'language' is a required property" in messages
        assert "'code' is a required property" in messages

    def test_schema_version_finding(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": "1.0.0", "triggers": [], "nodes": [], "edges": []}
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        assert result.error_count == 1
        assert result.findings[0].category == ValidationCategory.schema_version

    def test_missing_field_findings(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {"schema_version": "2.0.0"}
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        categories = [f.category for f in result.findings]
        assert all(c == ValidationCategory.missing_field for c in categories)
        assert result.error_count == 3

    def test_edge_reference_finding(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "1"}}],
            "edges": [{"from": "t1", "to": "ghost"}],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        ref_findings = [f for f in result.findings if f.category == ValidationCategory.invalid_reference]
        assert len(ref_findings) == 1
        assert ref_findings[0].node_id == "ghost"

    def test_cycle_finding(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "cycle",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "a", "type": "script", "parameters": {"language": "python", "code": "1"}},
                {"id": "b", "type": "script", "parameters": {"language": "python", "code": "2"}},
            ],
            "edges": [
                {"from": "t1", "to": "a"},
                {"from": "a", "to": "b"},
                {"from": "b", "to": "a"},
            ],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        cycle_findings = [f for f in result.findings if f.category == ValidationCategory.cycle_detected]
        assert len(cycle_findings) == 1

    def test_schema_errors_do_not_hide_structural_issues(self, validator: WorkflowValidator) -> None:
        """Schema errors and structural issues (orphan, cycle) accumulate in one pass."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "mixed-errors",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "n1", "type": "script", "parameters": {"language": "python", "code": "1"}},
                {"id": "n2", "type": "script", "config": {}},
                {"id": "orphan", "type": "script", "parameters": {"language": "python", "code": "3"}},
            ],
            "edges": [
                {"from": "t1", "to": "n1"},
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n1"},
            ],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        categories = {f.category for f in result.findings}
        assert ValidationCategory.schema_violation in categories
        assert ValidationCategory.orphaned_node in categories
        assert ValidationCategory.cycle_detected in categories

    def test_empty_nodes_allowed_for_save(self, validator: WorkflowValidator) -> None:
        """Empty nodes are allowed by the validator (canvas-first save). Publish blocks separately."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "empty-nodes",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }
        result = validator.collect_findings(definition)
        empty_findings = [f for f in result.findings if "at least one step" in f.message]
        assert len(empty_findings) == 0

    def test_unrecognized_node_type_produces_finding(self, validator: WorkflowValidator) -> None:
        """Unknown node type falls back to the top-level oneOf message."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "totally_fake_type", "parameters": {}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        assert result.is_valid is False
        schema_findings = [f for f in result.findings if f.category == ValidationCategory.schema_violation]
        assert any("not valid under any of the given schemas" in f.message for f in schema_findings)

    def test_empty_string_field_includes_field_path(self, validator: WorkflowValidator) -> None:
        """Empty-string schema violations carry field_path (AAP-82550 regression)."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"code": "", "language": "python"}}],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        code_findings = [f for f in result.findings if "non-empty" in f.message]
        assert len(code_findings) == 1
        assert code_findings[0].node_id == "n1"
        assert code_findings[0].field_path == "parameters.code"

    def test_json_serialization_shape(self, validator: WorkflowValidator) -> None:
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "1"}}],
            "edges": [{"from": "t1", "to": "ghost"}],
        }
        result = validator.collect_findings(definition)
        data = result.model_dump(mode="json")
        assert "is_valid" in data
        assert "error_count" in data
        assert "warning_count" in data
        assert "findings" in data
        finding = data["findings"][0]
        assert set(finding.keys()) == {"severity", "category", "message", "node_id", "field_path"}


def _converge_definition(
    converge_params: dict[str, Any] | None = None,
    predecessor_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a workflow with a converge node and configurable predecessors."""
    if predecessor_ids is None:
        predecessor_ids = ["branch_a", "branch_b"]

    nodes: list[dict[str, Any]] = [
        {"id": pid, "name": f"Branch {pid}", "type": "script", "parameters": {"language": "python", "code": "pass"}}
        for pid in predecessor_ids
    ]
    converge_node: dict[str, Any] = {
        "id": "converge_1",
        "name": "Converge",
        "type": "converge",
        "parameters": converge_params if converge_params is not None else {},
    }
    nodes.append(converge_node)

    edges: list[dict[str, Any]] = [{"from": "t1", "to": predecessor_ids[0]}] if predecessor_ids else []
    for i, pid in enumerate(predecessor_ids):
        if i > 0:
            edges.append({"from": "t1", "to": pid})
        edges.append({"from": pid, "to": "converge_1"})

    return {
        "schema_version": "2.0.0",
        "name": "converge-test",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": edges,
    }


class TestConvergeNodeValidation:
    """Converge node validation against graph structure."""

    def test_converge_two_predecessors_valid(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(_converge_definition())
        converge_findings = [f for f in result.findings if f.category == ValidationCategory.converge_configuration]
        assert converge_findings == []

    def test_converge_zero_predecessors_error(self, validator: WorkflowValidator) -> None:
        definition = _converge_definition(predecessor_ids=[])
        definition["edges"] = []
        result = validator.collect_findings(definition)
        converge_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.converge_configuration and f.severity == ValidationSeverity.error
        ]
        assert len(converge_errors) == 1
        assert converge_errors[0].node_id == "converge_1"
        assert "no incoming edges" in converge_errors[0].message

    def test_converge_one_predecessor_error(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(_converge_definition(predecessor_ids=["branch_a"]))
        converge_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.converge_configuration and f.severity == ValidationSeverity.error
        ]
        assert len(converge_errors) == 1
        assert converge_errors[0].node_id == "converge_1"
        assert "only 1 incoming branch" in converge_errors[0].message

    def test_converge_any_n_required_exceeds_branches(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(
            _converge_definition(
                converge_params={"strategy": "any", "n_required": 5},
                predecessor_ids=["branch_a", "branch_b"],
            )
        )
        n_req_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.converge_configuration and f.field_path == "parameters.n_required"
        ]
        assert len(n_req_errors) == 1
        assert "n_required (5)" in n_req_errors[0].message
        assert "incoming branches (2)" in n_req_errors[0].message

    def test_converge_any_n_required_within_limit(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(
            _converge_definition(
                converge_params={"strategy": "any", "n_required": 2},
                predecessor_ids=["branch_a", "branch_b", "branch_c"],
            )
        )
        converge_findings = [f for f in result.findings if f.category == ValidationCategory.converge_configuration]
        assert converge_findings == []

    def test_converge_all_strategy_ignores_n_required(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(
            _converge_definition(
                converge_params={"strategy": "all"},
                predecessor_ids=["branch_a", "branch_b"],
            )
        )
        n_req_errors = [f for f in result.findings if f.field_path == "parameters.n_required"]
        assert n_req_errors == []

    def test_converge_zero_preds_suppresses_n_required_error(self, validator: WorkflowValidator) -> None:
        """When a converge has 0 predecessors, only the missing-predecessors error fires."""
        definition = _converge_definition(
            converge_params={"strategy": "any", "n_required": 3},
            predecessor_ids=[],
        )
        definition["edges"] = []
        result = validator.collect_findings(definition)
        converge_findings = [f for f in result.findings if f.category == ValidationCategory.converge_configuration]
        assert len(converge_findings) == 1
        assert "no incoming edges" in converge_findings[0].message

    def test_converge_duplicate_edges_deduplicated(self, validator: WorkflowValidator) -> None:
        """Two edges from the same source (different ports) count as 1 unique predecessor."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "duplicate-edge-test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "cond", "type": "condition", "parameters": {"condition": "true"}},
                {"id": "converge_1", "type": "converge", "parameters": {}},
            ],
            "edges": [
                {"from": "t1", "to": "cond"},
                {"from": "cond", "to": "converge_1", "from_port": "true"},
                {"from": "cond", "to": "converge_1", "from_port": "false"},
            ],
        }
        result = validator.collect_findings(definition)
        converge_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.converge_configuration and f.severity == ValidationSeverity.error
        ]
        assert len(converge_errors) == 1
        assert converge_errors[0].node_id == "converge_1"
        assert "only 1 incoming branch" in converge_errors[0].message

    def test_converge_any_n_required_zero_rejected_by_schema(self, validator: WorkflowValidator) -> None:
        """n_required=0 is caught by JSON schema (minimum: 1) before graph checks run."""
        result = validator.collect_findings(
            _converge_definition(
                converge_params={"strategy": "any", "n_required": 0},
                predecessor_ids=["branch_a", "branch_b"],
            )
        )
        schema_errors = [f for f in result.findings if f.category == ValidationCategory.schema_violation]
        assert any("minimum" in f.message.lower() or "0" in f.message for f in schema_errors)

    def test_multiple_converge_nodes_independent(self, validator: WorkflowValidator) -> None:
        """Only the misconfigured converge gets findings."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "multi-converge",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "a", "type": "script", "parameters": {"language": "python", "code": "pass"}},
                {"id": "b", "type": "script", "parameters": {"language": "python", "code": "pass"}},
                {"id": "good_converge", "type": "converge", "parameters": {}},
                {"id": "bad_converge", "type": "converge", "parameters": {}},
            ],
            "edges": [
                {"from": "t1", "to": "a"},
                {"from": "t1", "to": "b"},
                {"from": "a", "to": "good_converge"},
                {"from": "b", "to": "good_converge"},
            ],
        }
        result = validator.collect_findings(definition)
        converge_findings = [f for f in result.findings if f.category == ValidationCategory.converge_configuration]
        assert len(converge_findings) == 1
        assert converge_findings[0].node_id == "bad_converge"


def _approval_definition(
    params: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal, port-valid workflow with an approval node.

    The approval node is wired to an ``approved``-port successor so the graph
    satisfies the approved-port requirement. Tests targeting that requirement
    build their own edges (see ``TestApprovalPortValidation``).
    """
    node: dict[str, Any] = {
        "id": "approval_1",
        "name": "Review",
        "type": "approval",
        "parameters": params if params is not None else {},
    }
    if settings is not None:
        node["settings"] = settings
    return {
        "schema_version": "2.0.0",
        "name": "approval-test",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            node,
            {
                "id": "after_approve",
                "name": "After Approve",
                "type": "script",
                "parameters": {"language": "python", "code": "pass"},
            },
        ],
        "edges": [
            {"from": "t1", "to": "approval_1"},
            {"from": "approval_1", "to": "after_approve", "from_port": "approved"},
        ],
    }


class TestApprovalNodeValidation:
    """Approval node parameter interplay warnings."""

    def test_fallback_without_cof_produces_warning(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(_approval_definition(params={"fallback_decision": "approve"}))
        warnings = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.warning
        ]
        assert len(warnings) == 1
        assert warnings[0].node_id == "approval_1"
        assert "fallback_decision" in warnings[0].message
        assert warnings[0].field_path == "parameters.fallback_decision"

    def test_fallback_approve_with_cof_no_warning(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(
            _approval_definition(
                params={"fallback_decision": "approve"},
                settings={"continue_on_failure": True},
            )
        )
        approval_findings = [f for f in result.findings if f.category == ValidationCategory.approval_configuration]
        assert approval_findings == []

    def test_fallback_reject_without_cof_no_warning(self, validator: WorkflowValidator) -> None:
        """Reject is the safe default — same outcome as no fallback (workflow fails)."""
        result = validator.collect_findings(_approval_definition(params={"fallback_decision": "reject"}))
        approval_findings = [f for f in result.findings if f.category == ValidationCategory.approval_configuration]
        assert approval_findings == []

    def test_no_fallback_no_warning(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(_approval_definition())
        approval_findings = [f for f in result.findings if f.category == ValidationCategory.approval_configuration]
        assert approval_findings == []

    def test_only_misconfigured_node_gets_warning(self, validator: WorkflowValidator) -> None:
        definition = _approval_definition(params={"fallback_decision": "approve"})
        definition["nodes"].append(
            {
                "id": "approval_2",
                "name": "Review 2",
                "type": "approval",
                "parameters": {"fallback_decision": "reject"},
                "settings": {"continue_on_failure": True},
            }
        )
        # approval_2 must also have an 'approved' successor to stay port-valid,
        # so the only approval finding is approval_1's fallback warning.
        definition["edges"].append({"from": "approval_1", "to": "approval_2", "from_port": "approved"})
        definition["edges"].append({"from": "approval_2", "to": "after_approve", "from_port": "approved"})
        result = validator.collect_findings(definition)
        warnings = [f for f in result.findings if f.category == ValidationCategory.approval_configuration]
        assert len(warnings) == 1
        assert warnings[0].node_id == "approval_1"

    def test_fallback_approve_with_system_cof_enabled_no_warning(self, validator: WorkflowValidator) -> None:
        """Node inherits system default (continue_on_failure=True) — no warning."""
        result = validator.collect_findings(
            _approval_definition(params={"fallback_decision": "approve"}),
            system_continue_on_failure=True,
        )
        approval_findings = [f for f in result.findings if f.category == ValidationCategory.approval_configuration]
        assert approval_findings == []

    def test_fallback_approve_with_system_cof_disabled_produces_warning(self, validator: WorkflowValidator) -> None:
        """Node inherits system default (continue_on_failure=False) — warning fires."""
        result = validator.collect_findings(
            _approval_definition(params={"fallback_decision": "approve"}),
            system_continue_on_failure=False,
        )
        warnings = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.warning
        ]
        assert len(warnings) == 1
        assert warnings[0].node_id == "approval_1"

    def test_node_explicit_cof_false_overrides_system_cof_true(self, validator: WorkflowValidator) -> None:
        """Node explicitly disables CoF — warning fires even if system default is True."""
        result = validator.collect_findings(
            _approval_definition(
                params={"fallback_decision": "approve"},
                settings={"continue_on_failure": False},
            ),
            system_continue_on_failure=True,
        )
        warnings = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.warning
        ]
        assert len(warnings) == 1
        assert warnings[0].node_id == "approval_1"

    def test_node_explicit_cof_true_overrides_system_cof_false(self, validator: WorkflowValidator) -> None:
        """Node explicitly enables CoF — no warning even if system default is False."""
        result = validator.collect_findings(
            _approval_definition(
                params={"fallback_decision": "approve"},
                settings={"continue_on_failure": True},
            ),
            system_continue_on_failure=False,
        )
        approval_findings = [f for f in result.findings if f.category == ValidationCategory.approval_configuration]
        assert approval_findings == []


class TestApprovalPortValidation:
    """Approval nodes require a successor on the 'approved' output port.

    Regression coverage: a portless approval workflow (the intuitive
    trigger -> approval -> next-step shape with plain edges) used to validate
    clean and then fail on every execution with a runtime error naming a port
    the author was never told about. collect_findings must surface this at
    save time, the way converge predecessor counts are validated.
    """

    def _portless_approval_definition(self) -> dict[str, Any]:
        """The intuitive-but-broken shape: a plain edge out of the approval node."""
        return {
            "schema_version": "2.0.0",
            "name": "repro-approval-no-port",
            "triggers": [{"id": "t_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "ap1", "name": "Review", "type": "approval", "parameters": {"prompt": "approve?"}},
                {"id": "s1", "type": "script", "parameters": {"language": "bash", "code": "echo next"}},
            ],
            "edges": [
                {"from": "t_manual", "to": "ap1"},
                {"from": "ap1", "to": "s1"},
            ],
        }

    def test_no_approved_port_is_error(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(self._portless_approval_definition())
        assert result.is_valid is False
        port_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.error
        ]
        assert len(port_errors) == 1
        assert port_errors[0].node_id == "ap1"
        assert "Approved" in port_errors[0].message
        assert "missing a connection" in port_errors[0].message

    def test_approved_port_present_no_error(self, validator: WorkflowValidator) -> None:
        definition = self._portless_approval_definition()
        definition["edges"] = [
            {"from": "t_manual", "to": "ap1"},
            {"from": "ap1", "to": "s1", "from_port": "approved"},
        ]
        result = validator.collect_findings(definition)
        approval_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.error
        ]
        assert approval_errors == []

    def test_rejected_only_still_errors(self, validator: WorkflowValidator) -> None:
        """A rejected-only successor does not satisfy the mandatory 'approved' port."""
        definition = self._portless_approval_definition()
        definition["nodes"].append(
            {"id": "s2", "type": "script", "parameters": {"language": "bash", "code": "echo rejected"}}
        )
        definition["edges"] = [
            {"from": "t_manual", "to": "ap1"},
            {"from": "ap1", "to": "s2", "from_port": "rejected"},
        ]
        result = validator.collect_findings(definition)
        port_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.error
        ]
        assert len(port_errors) == 1
        assert port_errors[0].node_id == "ap1"

    def test_both_ports_present_no_error(self, validator: WorkflowValidator) -> None:
        definition = self._portless_approval_definition()
        definition["nodes"].append(
            {"id": "s2", "type": "script", "parameters": {"language": "bash", "code": "echo rejected"}}
        )
        definition["edges"] = [
            {"from": "t_manual", "to": "ap1"},
            {"from": "ap1", "to": "s1", "from_port": "approved"},
            {"from": "ap1", "to": "s2", "from_port": "rejected"},
        ]
        result = validator.collect_findings(definition)
        approval_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.error
        ]
        assert approval_errors == []

    def test_only_offending_approval_node_flagged(self, validator: WorkflowValidator) -> None:
        """With two approval nodes, only the portless one is flagged."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "multi-approval",
            "triggers": [{"id": "t_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "ap_good", "type": "approval", "parameters": {"prompt": "a?"}},
                {"id": "ap_bad", "type": "approval", "parameters": {"prompt": "b?"}},
                {"id": "s1", "type": "script", "parameters": {"language": "bash", "code": "echo 1"}},
            ],
            "edges": [
                {"from": "t_manual", "to": "ap_good"},
                {"from": "ap_good", "to": "ap_bad", "from_port": "approved"},
                {"from": "ap_bad", "to": "s1"},
            ],
        }
        result = validator.collect_findings(definition)
        port_errors = [
            f
            for f in result.findings
            if f.category == ValidationCategory.approval_configuration and f.severity == ValidationSeverity.error
        ]
        assert len(port_errors) == 1
        assert port_errors[0].node_id == "ap_bad"


class TestScheduledTriggerConfigFindings:
    """collect_findings enforces ScheduledTriggerConfig (IANA timezone) beyond JSON Schema."""

    def _scheduled_definition(self, *, timezone: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"schedule_type": "cron", "cron": "0 9 * * *"}
        if timezone is not None:
            params["timezone"] = timezone
        return {
            "schema_version": "2.0.0",
            "name": "scheduled-wf",
            "triggers": [{"id": "sched_1", "type": "scheduled_trigger", "parameters": params}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_1", "to": "n1"}],
        }

    def _interval_definition(self, *, interval: str) -> dict[str, Any]:
        return {
            "schema_version": "2.0.0",
            "name": "interval-wf",
            "triggers": [
                {
                    "id": "sched_1",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "interval", "interval": interval},
                }
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_1", "to": "n1"}],
        }

    def test_invalid_interval_is_error(self, validator: WorkflowValidator) -> None:
        """An unparseable interval must fail collect_findings, not only publish."""
        result = validator.collect_findings(self._interval_definition(interval="not-an-interval"))
        assert result.is_valid is False
        scheduled = [f for f in result.findings if "scheduled trigger config" in f.message]
        assert len(scheduled) == 1
        assert scheduled[0].node_id == "sched_1"
        assert scheduled[0].field_path == "parameters.interval"

    def test_valid_interval_passes(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(self._interval_definition(interval="R/2024-01-01T10:00:00Z/P1D"))
        assert result.is_valid is True
        assert result.findings == []

    def test_invalid_iana_timezone_is_error(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(self._scheduled_definition(timezone="Invalid/Not_A_Real_Zone"))
        assert result.is_valid is False
        scheduled = [f for f in result.findings if "scheduled trigger config" in f.message]
        assert len(scheduled) == 1
        assert scheduled[0].node_id == "sched_1"
        assert scheduled[0].field_path == "parameters.timezone"

    def test_valid_iana_timezone_passes(self, validator: WorkflowValidator) -> None:
        result = validator.collect_findings(self._scheduled_definition(timezone="America/New_York"))
        assert result.is_valid is True
        assert result.findings == []

    def test_multiple_invalid_triggers_accumulate_findings(self, validator: WorkflowValidator) -> None:
        definition = {
            "schema_version": "2.0.0",
            "name": "multi-scheduled-wf",
            "triggers": [
                {
                    "id": "sched_a",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 9 * * *", "timezone": "Fake/A"},
                },
                {
                    "id": "sched_b",
                    "type": "scheduled_trigger",
                    "parameters": {"schedule_type": "cron", "cron": "0 10 * * *", "timezone": "Fake/B"},
                },
            ],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "pass"}}],
            "edges": [{"from": "sched_a", "to": "n1"}, {"from": "sched_b", "to": "n1"}],
        }
        result = validator.collect_findings(definition)
        scheduled = [f for f in result.findings if "scheduled trigger config" in f.message]
        assert result.is_valid is False
        assert len(scheduled) == 2
        assert {f.node_id for f in scheduled} == {"sched_a", "sched_b"}
        assert all(f.field_path == "parameters.timezone" for f in scheduled)


class TestBestBranchMessages:
    """Direct tests for _best_branch_messages edge cases."""

    def test_no_context_returns_parent_message_and_path(self) -> None:
        """Error with no oneOf context returns the error's own message and path."""
        definition: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [{"id": "n1", "type": "script", "parameters": {"language": "python", "code": "x"}}],
            "edges": [{"from": "t1", "to": "n1", "color": "red"}],
        }
        from syntara.workflows.validators.workflow_definition import _get_validator

        for error in _get_validator().iter_errors(definition):
            if not error.context:
                result = _best_branch_messages(error)
                assert len(result) == 1
                msg, path = result[0]
                assert "color" in msg
                assert path == list(error.absolute_path)
                return
        pytest.fail("Expected a no-context error for additional property")
