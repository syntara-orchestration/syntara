"""Tests for template expression validation in workflow definitions."""

import importlib
from typing import Any

import pytest

import syntara.workflows.validators.template_expressions
from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.validators.template_expressions import (
    _extract_element_expressions,
    _extract_expressions,
    _identify_loop_body_nodes,
    check_template_expressions,
)


class TestModuleLevelCoverage:
    """Reload the module so coverage tracks the module-level constants and imports."""

    def test_module_reload_covers_constants(self) -> None:
        importlib.reload(syntara.workflows.validators.template_expressions)


def _base_definition(**overrides: object) -> dict[str, Any]:
    """Build a minimal valid workflow definition with overridable fields."""
    defn: dict[str, Any] = {
        "schema_version": "2.0.0",
        "name": "test",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [],
        "edges": [],
    }
    defn.update(overrides)
    return defn


def _script_node(node_id: str, **extra_params: object) -> dict[str, Any]:
    params: dict[str, Any] = {"language": "python", "code": "print(1)"}
    params.update(extra_params)
    return {"id": node_id, "type": "script", "parameters": params}


def _http_node(node_id: str, **extra_params: object) -> dict[str, Any]:
    params: dict[str, Any] = {"method": "GET", "url": "https://example.com"}
    params.update(extra_params)
    return {"id": node_id, "type": "http_request", "parameters": params}


def _condition_node(node_id: str, condition: str) -> dict[str, Any]:
    return {"id": node_id, "type": "condition", "parameters": {"condition": condition}}


def _loop_definition(
    body_nodes: list[dict[str, Any]],
    loop_id: str = "loop_node",
    loop_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a workflow with a loop node and body nodes wired correctly."""
    loop = {
        "id": loop_id,
        "type": "loop",
        "parameters": loop_params or {"type": "for_each", "items": "${trigger.items}"},
    }
    converge = {"id": "converge_node", "type": "converge", "parameters": {}}
    nodes = [loop, *body_nodes, converge]
    edges: list[dict[str, Any]] = [
        {"from": "t1", "to": loop_id},
        {"from": loop_id, "to": body_nodes[0]["id"], "from_port": "iterate"},
    ]
    for i in range(len(body_nodes) - 1):
        edges.append({"from": body_nodes[i]["id"], "to": body_nodes[i + 1]["id"]})
    last_body = body_nodes[-1]["id"]
    edges.append({"from": last_body, "to": loop_id, "to_port": "iterate"})
    edges.append({"from": loop_id, "to": "converge_node", "from_port": "complete"})
    return _base_definition(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# AC1: Unresolved activity reference
# ---------------------------------------------------------------------------
class TestUnresolvedActivityReference:
    """Expressions referencing a non-existent activity produce errors."""

    def test_nonexistent_node_in_parameter(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": "${ghost.output}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert isinstance(errors[0], ValidationFinding)
        assert errors[0].node_id == "n1"
        assert errors[0].severity == ValidationSeverity.error
        assert errors[0].category == ValidationCategory.invalid_reference
        assert "ghost" in errors[0].message
        assert "${ghost.output}" in errors[0].message

    def test_nonexistent_node_in_condition(self) -> None:
        defn = _base_definition(
            nodes=[_condition_node("cond1", "${missing.status} == 'ok'")],
            edges=[{"from": "t1", "to": "cond1"}],
        )
        node_ids = {"t1", "cond1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "missing" in errors[0].message

    def test_nonexistent_node_in_nested_body(self) -> None:
        defn = _base_definition(
            nodes=[
                _http_node(
                    "req1",
                    body={"nested": {"deep": "${phantom.value}"}},
                ),
            ],
            edges=[{"from": "t1", "to": "req1"}],
        )
        node_ids = {"t1", "req1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "phantom" in errors[0].message

    def test_multiple_unresolved_references(self) -> None:
        defn = _base_definition(
            nodes=[
                _http_node(
                    "req1",
                    headers={"A": "${ghost_a.x}"},
                    body={"key": "${ghost_b.y}"},
                ),
            ],
            edges=[{"from": "t1", "to": "req1"}],
        )
        node_ids = {"t1", "req1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 2
        messages = " ".join(e.message for e in errors)
        assert "ghost_a" in messages
        assert "ghost_b" in messages


# ---------------------------------------------------------------------------
# AC2: Invalid namespace scope
# ---------------------------------------------------------------------------
class TestInvalidNamespaceScope:
    """Expressions with completely invalid scopes produce errors."""

    def test_loop_variable_outside_loop_produces_error(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": "${loop.item}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert isinstance(errors[0], ValidationFinding)
        assert errors[0].severity == ValidationSeverity.error
        assert errors[0].category == ValidationCategory.invalid_reference
        assert "loop" in errors[0].message
        assert "outside" in errors[0].message
        assert errors[0].node_id == "n1"

    def test_bare_item_outside_loop_produces_error(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": "${item}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "item" in errors[0].message

    def test_bare_iteration_index_outside_loop_produces_error(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": "${iteration_index}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "iteration_index" in errors[0].message

    @pytest.mark.parametrize(
        ("expression", "scope"),
        [
            ("${variables.count}", "variables"),
            ("${input.env}", "input"),
            ("${inputs.env}", "inputs"),
        ],
    )
    def test_unknown_names_are_rejected_like_missing_nodes(self, expression: str, scope: str) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": expression})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert errors[0].category == ValidationCategory.invalid_reference
        assert scope in errors[0].message
        assert "unknown activity or scope" in errors[0].message
        assert "leftover V1" not in errors[0].message

    @pytest.mark.parametrize("node_id", ["input", "inputs", "variables"])
    def test_node_named_reserved_word_is_a_valid_reference(self, node_id: str) -> None:
        defn = _base_definition(
            nodes=[
                _script_node(node_id),
                _script_node("n1", environment={"X": f"${{{node_id}.stdout}}"}),
            ],
            edges=[{"from": "t1", "to": node_id}, {"from": node_id, "to": "n1"}],
        )
        errors = check_template_expressions(defn, {"t1", node_id, "n1"})
        assert errors == []


# ---------------------------------------------------------------------------
# AC3: All valid expressions produce no findings
# ---------------------------------------------------------------------------
class TestAllValidExpressions:
    """Valid expressions produce no errors or warnings."""

    @pytest.mark.parametrize(
        "expression",
        [
            "${trigger.data}",
            "${workflow_context.execution.id}",
            "${workflow_context.now}",
            "${workflow_context.today}",
        ],
    )
    def test_builtin_scope_valid(self, expression: str) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": expression})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_existing_activity_reference(self) -> None:
        defn = _base_definition(
            nodes=[
                _script_node("step1"),
                _script_node("step2", environment={"X": "${step1.stdout}"}),
            ],
            edges=[
                {"from": "t1", "to": "step1"},
                {"from": "step1", "to": "step2"},
            ],
        )
        node_ids = {"t1", "step1", "step2"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_no_template_expressions(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1")],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_trigger_id_as_scope(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": "${t1.result.value}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []


# ---------------------------------------------------------------------------
# AC4: Nested field discovery
# ---------------------------------------------------------------------------
class TestNestedFieldDiscovery:
    """Expressions in nested config fields are discovered and validated."""

    def test_http_body_nested_dict(self) -> None:
        defn = _base_definition(
            nodes=[
                _http_node(
                    "req1",
                    body={
                        "outer": {
                            "inner": "${ghost.value}",
                        },
                    },
                ),
            ],
            edges=[{"from": "t1", "to": "req1"}],
        )
        node_ids = {"t1", "req1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "ghost" in errors[0].message

    def test_http_headers_validated(self) -> None:
        defn = _base_definition(
            nodes=[
                _http_node(
                    "req1",
                    headers={"Authorization": "Bearer ${ghost_token.value}"},
                ),
            ],
            edges=[{"from": "t1", "to": "req1"}],
        )
        node_ids = {"t1", "req1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1

    def test_script_environment_validated(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"KEY": "${ghost.val}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1

    def test_expressions_in_list_values(self) -> None:
        defn = _base_definition(
            nodes=[
                _http_node("req1", body=["${ghost_a.x}", "${ghost_b.y}"]),
            ],
            edges=[{"from": "t1", "to": "req1"}],
        )
        node_ids = {"t1", "req1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 2

    def test_multiple_expressions_in_single_string(self) -> None:
        defn = _base_definition(
            nodes=[
                _http_node("req1", url="${ghost_a.host}:${ghost_b.port}/api"),
            ],
            edges=[{"from": "t1", "to": "req1"}],
        )
        node_ids = {"t1", "req1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 2


# ---------------------------------------------------------------------------
# AC5: Loop-specific variables
# ---------------------------------------------------------------------------
class TestLoopVariables:
    """Loop variables are valid inside loop body nodes."""

    def test_loop_item_in_body_valid(self) -> None:
        body = [_script_node("body1", environment={"X": "${loop.item}"})]
        defn = _loop_definition(body)
        node_ids = {"t1", "loop_node", "body1", "converge_node"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_loop_index_in_body_valid(self) -> None:
        body = [_script_node("body1", environment={"X": "${loop.index}"})]
        defn = _loop_definition(body)
        node_ids = {"t1", "loop_node", "body1", "converge_node"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_loop_with_node_id_in_body_valid(self) -> None:
        body = [_script_node("body1", environment={"X": "${loop.loop_node.item}"})]
        defn = _loop_definition(body)
        node_ids = {"t1", "loop_node", "body1", "converge_node"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_bare_item_in_body_produces_error(self) -> None:
        body = [_script_node("body1", environment={"X": "${item}"})]
        defn = _loop_definition(body)
        node_ids = {"t1", "loop_node", "body1", "converge_node"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "item" in errors[0].message

    def test_bare_iteration_index_in_body_produces_error(self) -> None:
        body = [_script_node("body1", environment={"X": "${iteration_index}"})]
        defn = _loop_definition(body)
        node_ids = {"t1", "loop_node", "body1", "converge_node"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "iteration_index" in errors[0].message

    def test_nested_inner_loop_can_use_loop_scope(self) -> None:
        inner_loop: dict[str, Any] = {
            "id": "inner_loop",
            "type": "loop",
            "parameters": {"type": "for_each", "items": "${loop.item.children}"},
        }
        inner_body = _script_node("inner_body", environment={"X": "${loop.item}"})
        defn = _base_definition(
            nodes=[
                {"id": "outer_loop", "type": "loop", "parameters": {"type": "for_each", "items": "${trigger.items}"}},
                inner_loop,
                inner_body,
                {"id": "converge_node", "type": "converge", "parameters": {}},
            ],
            edges=[
                {"from": "t1", "to": "outer_loop"},
                {"from": "outer_loop", "to": "inner_loop", "from_port": "iterate"},
                {"from": "inner_loop", "to": "inner_body", "from_port": "iterate"},
                {"from": "inner_body", "to": "inner_loop", "to_port": "iterate"},
                {"from": "inner_loop", "to": "outer_loop", "to_port": "iterate"},
                {"from": "outer_loop", "to": "converge_node", "from_port": "complete"},
            ],
        )
        node_ids = {"t1", "outer_loop", "inner_loop", "inner_body", "converge_node"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_loop_scope_outside_body_errors(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"X": "${loop.item}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "loop" in errors[0].message
        assert "outside" in errors[0].message


# ---------------------------------------------------------------------------
# Skip fields
# ---------------------------------------------------------------------------
class TestSkipFields:
    """Fields excluded from template expression validation."""

    def test_script_code_field_skipped(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", code="${shell_var} is fine in code")],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_script_environment_not_skipped(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1", environment={"K": "${ghost.v}"})],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1

    def test_outputs_field_not_scanned(self) -> None:
        node = _script_node("n1")
        node["outputs"] = {"val": "${result.value}"}
        defn = _base_definition(
            nodes=[node],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []


# ---------------------------------------------------------------------------
# Loop body detection
# ---------------------------------------------------------------------------
class TestLoopBodyDetection:
    """_identify_loop_body_nodes correctly maps body membership."""

    def test_simple_body(self) -> None:
        defn = _loop_definition([_script_node("body1")])
        result = _identify_loop_body_nodes(defn)
        assert result == {"body1": "loop_node"}

    def test_transitive_body(self) -> None:
        defn = _loop_definition([_script_node("body1"), _script_node("body2")])
        result = _identify_loop_body_nodes(defn)
        assert result["body1"] == "loop_node"
        assert result["body2"] == "loop_node"

    def test_converge_not_in_body(self) -> None:
        defn = _loop_definition([_script_node("body1")])
        result = _identify_loop_body_nodes(defn)
        assert "converge_node" not in result

    def test_no_loops_returns_empty(self) -> None:
        defn = _base_definition(
            nodes=[_script_node("n1")],
            edges=[{"from": "t1", "to": "n1"}],
        )
        result = _identify_loop_body_nodes(defn)
        assert result == {}


# ---------------------------------------------------------------------------
# Expression extraction helpers
# ---------------------------------------------------------------------------
class TestExtractExpressions:
    """_extract_expressions finds expressions in nested structures."""

    def test_string_with_expression(self) -> None:
        result = _extract_expressions("${step_1.name}", "field")
        assert result == [("step_1.name", "field")]

    def test_string_with_multiple_expressions(self) -> None:
        result = _extract_expressions("${a.x} and ${b.y}", "field")
        assert len(result) == 2

    def test_nested_dict(self) -> None:
        result = _extract_expressions({"a": {"b": "${x.y}"}}, "root")
        assert result == [("x.y", "root.a.b")]

    def test_list_values(self) -> None:
        result = _extract_expressions(["${a.x}", "${b.y}"], "items")
        assert len(result) == 2
        assert result[0] == ("a.x", "items[0]")
        assert result[1] == ("b.y", "items[1]")

    def test_no_expressions_returns_empty(self) -> None:
        result = _extract_expressions("plain text", "field")
        assert result == []

    def test_deeply_nested_structure_stops_at_depth_limit(self) -> None:
        nested: Any = "${deep.value}"
        for _ in range(60):
            nested = {"level": nested}
        result = _extract_expressions(nested, "root")
        assert result == []

    def test_non_string_primitives_return_empty(self) -> None:
        assert _extract_expressions(42, "field") == []
        bool_val: object = True
        assert _extract_expressions(bool_val, "field") == []
        assert _extract_expressions(None, "field") == []


class TestExtractElementExpressions:
    """_extract_element_expressions respects skip rules."""

    def test_skips_code_field_for_script(self) -> None:
        node = _script_node("n1", code="${something}")
        result = _extract_element_expressions(node)
        codes = [expr for expr, _ in result if "something" in expr]
        assert codes == []

    def test_includes_environment_for_script(self) -> None:
        node = _script_node("n1", environment={"K": "${step_1.val}"})
        result = _extract_element_expressions(node)
        assert len(result) == 1
        assert result[0][0] == "step_1.val"

    def test_node_without_type_uses_empty_skip(self) -> None:
        node: dict[str, Any] = {"id": "n1", "parameters": {"url": "${ghost.val}"}}
        result = _extract_element_expressions(node)
        assert len(result) == 1
        assert result[0][0] == "ghost.val"

    def test_node_with_empty_parameters(self) -> None:
        node: dict[str, Any] = {"id": "n1", "type": "http_request", "parameters": {}}
        result = _extract_element_expressions(node)
        assert result == []


# ---------------------------------------------------------------------------
# Trigger expression validation
# ---------------------------------------------------------------------------
class TestTriggerExpressions:
    """Expressions in triggers are validated alongside nodes."""

    def test_invalid_expression_in_trigger(self) -> None:
        defn = _base_definition(
            triggers=[
                {
                    "id": "t1",
                    "type": "webhook",
                    "parameters": {"transform": "${ghost.value}"},
                },
            ],
            nodes=[_script_node("n1")],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert len(errors) == 1
        assert "ghost" in errors[0].message

    def test_valid_builtin_expression_in_trigger(self) -> None:
        defn = _base_definition(
            triggers=[
                {
                    "id": "t1",
                    "type": "webhook",
                    "parameters": {"value": "${trigger.data}"},
                },
            ],
            nodes=[_script_node("n1")],
            edges=[{"from": "t1", "to": "n1"}],
        )
        node_ids = {"t1", "n1"}
        errors = check_template_expressions(defn, node_ids)
        assert errors == []

    def test_empty_workflow_produces_no_findings(self) -> None:
        defn = _base_definition(nodes=[], edges=[])
        errors = check_template_expressions(defn, {"t1"})
        assert errors == []
