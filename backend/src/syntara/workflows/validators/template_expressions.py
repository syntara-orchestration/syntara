"""Template expression validation for V2 workflow definitions.

Validates that ``${...}`` expressions in node parameters reference valid
scopes and existing activity/trigger IDs. Sub-workflow output fields are
checked against their model except for dynamic child entries under
``Result.outputs``.
"""

import re
from collections import deque
from typing import Any

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.workflow_engine.models.workflow_definition import (
    SubWorkflowOutput,
    SubWorkflowOutputResult,
)

TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Keep in sync with KNOWN_NAMESPACES in
# frontend/packages/syntara-ui/src/routes/builder/utils/validation/rules/validateVariableReferences.ts
BUILTIN_SCOPES: frozenset[str] = frozenset(
    {
        "trigger",
        "workflow_context",
    }
)

_SKIP_FIELDS_BY_NODE_TYPE: dict[str, frozenset[str]] = {
    "script": frozenset({"code"}),
}

_SUBWORKFLOW_OUTPUT_FIELDS = frozenset(SubWorkflowOutput.model_fields)
_SUBWORKFLOW_RESULT_FIELDS = frozenset(SubWorkflowOutputResult.model_fields)


def _validate_subworkflow_output_path(
    expr_body: str,
    node_id: str | None,
    field_path: str,
) -> ValidationFinding | None:
    """Validate static Sub-workflow output fields, leaving ``Result.outputs`` dynamic."""
    _, *path = expr_body.split(".")
    if not path:
        return None

    output_field, *path = path
    if output_field not in _SUBWORKFLOW_OUTPUT_FIELDS:
        message = f"Expression '${{{expr_body}}}' references unknown Sub-workflow output field '{output_field}'"
    elif output_field != "Result" and path:
        message = f"Expression '${{{expr_body}}}' cannot access a nested field through '{output_field}'"
    elif output_field == "Result" and path:
        result_field, *path = path
        if result_field not in _SUBWORKFLOW_RESULT_FIELDS:
            message = f"Expression '${{{expr_body}}}' references unknown Sub-workflow Result field '{result_field}'"
        elif result_field == "outputs":
            return None
        elif path:
            message = f"Expression '${{{expr_body}}}' cannot access a nested field through 'Result.{result_field}'"
        else:
            return None
    else:
        return None

    return ValidationFinding(
        severity=ValidationSeverity.error,
        category=ValidationCategory.invalid_reference,
        message=message,
        node_id=node_id,
        field_path=field_path,
    )


def _identify_loop_body_nodes(workflow_definition: dict[str, Any]) -> dict[str, str]:
    """Build a mapping of ``{node_id: loop_node_id}`` for nodes inside loop bodies.

    Walks edges from each loop node's ``from_port="iterate"`` successors via BFS,
    stopping at feedback edges (``to_port="iterate"``) back to the loop.
    """
    loop_node_ids = {n["id"] for n in workflow_definition.get("nodes", []) if n.get("type") == "loop"}
    if not loop_node_ids:
        return {}

    adjacency: dict[str, list[str]] = {}
    iterate_successors: dict[str, list[str]] = {}
    feedback_edges: set[tuple[str, str]] = set()

    for edge in workflow_definition.get("edges", []):
        src, dst = edge["from"], edge["to"]
        if edge.get("to_port") == "iterate":
            feedback_edges.add((src, dst))
            continue
        adjacency.setdefault(src, []).append(dst)
        if src in loop_node_ids and edge.get("from_port") == "iterate":
            iterate_successors.setdefault(src, []).append(dst)

    loop_body_map: dict[str, str] = {}
    for loop_id, seeds in iterate_successors.items():
        queue: deque[str] = deque(seeds)
        while queue:
            nid = queue.popleft()
            if nid in loop_body_map or nid == loop_id:
                continue
            loop_body_map[nid] = loop_id
            for successor in adjacency.get(nid, []):
                if (nid, successor) not in feedback_edges:
                    queue.append(successor)
    return loop_body_map


_MAX_NESTING_DEPTH = 50


def _extract_expressions(value: Any, path_prefix: str, *, _depth: int = 0) -> list[tuple[str, str]]:  # noqa: ANN401
    """Recursively extract ``${...}`` expressions from nested dicts, lists, and strings.

    Returns:
        List of ``(expression_body, field_path)`` pairs.

    """
    if _depth >= _MAX_NESTING_DEPTH:
        return []
    results: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, val in value.items():
            child_path = f"{path_prefix}.{key}" if path_prefix else key
            results.extend(_extract_expressions(val, child_path, _depth=_depth + 1))
    elif isinstance(value, list):
        for idx, val in enumerate(value):
            child_path = f"{path_prefix}[{idx}]"
            results.extend(_extract_expressions(val, child_path, _depth=_depth + 1))
    elif isinstance(value, str):
        results.extend((match.group(1), path_prefix) for match in TEMPLATE_PATTERN.finditer(value))
    return results


def extract_element_expressions(
    node: dict[str, Any],
) -> list[tuple[str, str]]:
    """Extract template expressions from an element's parameters, skipping excluded fields."""
    node_type = node.get("type", "")
    skip_fields = _SKIP_FIELDS_BY_NODE_TYPE.get(node_type, frozenset())

    params = node.get("parameters", {})
    if not isinstance(params, dict):
        return []
    results: list[tuple[str, str]] = []
    for key, val in params.items():
        if key in skip_fields:
            continue
        results.extend(_extract_expressions(val, f"parameters.{key}"))
    return results


def check_template_expressions(
    workflow_definition: dict[str, Any],
    node_ids: set[str],
) -> list[ValidationFinding]:
    """Validate template expressions in all nodes and triggers.

    Returns:
        List of validation findings for invalid expressions.

    """
    loop_body_map = _identify_loop_body_nodes(workflow_definition)
    findings: list[ValidationFinding] = []

    all_elements = [
        *workflow_definition.get("triggers", []),
        *workflow_definition.get("nodes", []),
    ]
    subworkflow_node_ids = {
        element.get("id")
        for element in workflow_definition.get("nodes", [])
        if isinstance(element, dict) and element.get("type") == "sub_workflow" and isinstance(element.get("id"), str)
    }
    for element in all_elements:
        if not isinstance(element, dict):
            continue
        element_id = element.get("id")
        expressions = extract_element_expressions(element)
        in_loop_body = element_id in loop_body_map

        for expr_body, field_path in expressions:
            scope = expr_body.split(".")[0]

            if scope in BUILTIN_SCOPES:
                continue

            if scope in node_ids:
                if scope in subworkflow_node_ids:
                    finding = _validate_subworkflow_output_path(expr_body, element_id, field_path)
                    if finding is not None:
                        findings.append(finding)
                continue

            if scope == "loop":
                if in_loop_body:
                    continue
                findings.append(
                    ValidationFinding(
                        severity=ValidationSeverity.error,
                        category=ValidationCategory.invalid_reference,
                        message=(f"Expression '${{{expr_body}}}' uses loop scope outside of a loop body"),
                        node_id=element_id,
                    )
                )
                continue

            findings.append(
                ValidationFinding(
                    severity=ValidationSeverity.error,
                    category=ValidationCategory.invalid_reference,
                    message=(f"Expression '${{{expr_body}}}' references unknown activity or scope '{scope}'"),
                    node_id=element_id,
                )
            )

    return findings
