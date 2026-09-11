"""Template expression validation for V2 workflow definitions.

Validates that ``${...}`` expressions in node parameters reference valid
scopes and existing activity/trigger IDs.  Produces errors for unresolved
activity references and invalid namespace scopes.
"""

import re
from collections import deque
from typing import Any

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity

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


def _extract_element_expressions(
    node: dict[str, Any],
) -> list[tuple[str, str]]:
    """Extract template expressions from an element's parameters, skipping excluded fields."""
    node_type = node.get("type", "")
    skip_fields = _SKIP_FIELDS_BY_NODE_TYPE.get(node_type, frozenset())

    params = node.get("parameters", {})
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
    for element in all_elements:
        element_id = element.get("id")
        expressions = _extract_element_expressions(element)
        in_loop_body = element_id in loop_body_map

        for expr_body, _field_path in expressions:
            scope = expr_body.split(".")[0]

            if scope in BUILTIN_SCOPES:
                continue

            if scope in node_ids:
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
