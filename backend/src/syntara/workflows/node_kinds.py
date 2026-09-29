"""Canonical workflow step-kind registry used by authorization policy generation."""

from typing import Any

from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

NODE_RESOURCE_TYPE = "workflow_node"
NODE_KIND_LABEL = "kind"
NODE_ACTION_EXECUTE = "execute"
NODE_KINDS = tuple(node_type.value for node_type in NodeType)
REGISTERED_STEP_KINDS = NODE_KINDS
_KIND_SET = frozenset(NODE_KINDS)


def get_node_kind(kind: str) -> str | None:
    """Return the registered step kind, if present."""
    return kind if kind in _KIND_SET else None


def node_kind_action_pairs() -> frozenset[tuple[str, str]]:
    """Return the only supported workflow-node authorization action."""
    return frozenset({(NODE_RESOURCE_TYPE, NODE_ACTION_EXECUTE)})


def validate_node_kind_statements(statements: list[dict[str, Any]]) -> str | None:
    """Require step policies to use execute, a known kind, and only the kind label."""
    for statement in statements:
        actions = [
            action.split(":", maxsplit=1)[1]
            for action in statement.get("actions", [])
            if action.startswith(f"{NODE_RESOURCE_TYPE}:")
        ]
        if not actions:
            continue
        if actions != [NODE_ACTION_EXECUTE]:
            return "workflow_node supports only the execute action"
        conditions = statement.get("conditions") or {}
        labels = conditions.get("resource_labels") or {}
        if set(labels) != {NODE_KIND_LABEL}:
            return "workflow_node policies require only conditions.resource_labels.kind"
        kind = labels[NODE_KIND_LABEL]
        if not isinstance(kind, str) or get_node_kind(kind) is None:
            return f"Unknown node kind '{kind}'. Registered kinds: {', '.join(NODE_KINDS)}"
        if conditions.get("resource_labels_not"):
            return "workflow_node policies do not support negated resource labels"
    return None
