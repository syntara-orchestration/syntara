"""Step-type identifiers and labels for authoring policies.

Every NodeType is a valid ``kind`` on the ``step_type:write`` resource.
Registration does not enforce permissions on workflow writes.
"""

from typing import Any

from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

NODE_RESOURCE_TYPE = "step_type"
NODE_KIND_LABEL = "kind"
NODE_ACTION_WRITE = "write"
NODE_KINDS: frozenset[str] = frozenset(node_type.value for node_type in NodeType)


def node_labels(node: dict[str, Any]) -> dict[str, str]:
    """Return the step type label without exposing step parameters."""
    kind = node.get("type")
    return {NODE_KIND_LABEL: kind} if isinstance(kind, str) and kind else {}


def _validate_kind_labels(labels: object, condition: str) -> str | None:
    if labels is None:
        return None
    if not isinstance(labels, dict):
        return f"Step type condition '{condition}' must be an object"
    unsupported = set(labels) - {NODE_KIND_LABEL}
    if unsupported:
        return f"Unsupported step type labels: {', '.join(sorted(unsupported))}. Only 'kind' is supported."
    if NODE_KIND_LABEL not in labels:
        return None
    kind = labels[NODE_KIND_LABEL]
    if not isinstance(kind, str) or kind not in NODE_KINDS:
        return f"Unknown step type '{kind}'. Registered step types: {', '.join(sorted(NODE_KINDS))}"
    return None


def validate_node_kind_statements(statements: list[dict[str, Any]]) -> str | None:
    """Reject invalid step labels, leaving conditions on other resources alone."""
    for statement in statements:
        if not any(action.partition(":")[0] == NODE_RESOURCE_TYPE for action in statement.get("actions", [])):
            continue
        conditions = statement.get("conditions")
        if conditions is None:
            continue
        if not isinstance(conditions, dict):
            return "Step type conditions must be an object"
        for condition in ("resource_labels", "resource_labels_not"):
            error = _validate_kind_labels(conditions.get(condition), condition)
            if error:
                return error
    return None
