"""Declarative registry of workflow node kinds (ANSTRAT-2533).

Single source of truth for *which node kinds exist* and what the
authorization layer may say about each of them.  Consumed by:

- the authz resource-actions registry, which exposes the ``workflow_node``
  resource type and marks it project-eligible;
- policy validation, which checks the ``kind`` label on ``workflow_node``
  statements against this registry.

Node kinds are not rows: the workflow definition is a JSONB blob and a
node's kind is an attribute of that blob.  The permission subject is the
``workflow_node`` resource type with the node kind carried as the ``kind``
label on the authorization input.

This module only *registers* the contract — nothing is enforced yet.  Later
stories add deny policies, enforcement on workflow saves and the add-step
panel gating.
"""

from __future__ import annotations

from typing import Any

from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

NODE_RESOURCE_TYPE = "workflow_node"
"""Resource type under which node kinds are authorized."""

NODE_KIND_LABEL = "kind"
"""Label key carrying the node kind on a ``workflow_node`` authorization input."""

NODE_ACTION_WRITE = "write"
"""Sole action defined for the ``workflow_node`` resource type: introducing
(or modifying) a step of that kind in a workflow definition."""

NODE_ACTIONS: frozenset[str] = frozenset({NODE_ACTION_WRITE})
"""Every action defined for the ``workflow_node`` resource type."""

NODE_KINDS: frozenset[str] = frozenset(node_type.value for node_type in NodeType)
"""Every registered node kind, derived from the ``NodeType`` enum."""


def all_node_kinds() -> frozenset[str]:
    """Return every registered node kind."""
    return NODE_KINDS


def is_known_node_kind(kind: str) -> bool:
    """Return ``True`` if *kind* is a registered node kind."""
    return kind in NODE_KINDS


def node_kind_action_pairs() -> frozenset[tuple[str, str]]:
    """Return the ``(resource_type, action)`` pairs contributed to the authz registry."""
    return frozenset((NODE_RESOURCE_TYPE, action) for action in NODE_ACTIONS)


def _targets_workflow_node(actions: list[str]) -> bool:
    """Return ``True`` when any action string targets the ``workflow_node`` resource type.

    The ``workflow_node:*`` wildcard is included.
    """
    for action_str in actions:
        resource_type, _, action = action_str.partition(":")
        if resource_type == NODE_RESOURCE_TYPE and action:
            return True
    return False


def validate_node_kind_statements(statements: list[dict[str, Any]]) -> str | None:
    """Validate the ``kind`` label on ``workflow_node`` policy statements.

    Labels are free-form everywhere else in the system; for node kinds a
    typo would silently match nothing, so the value is checked against the
    registry.

    Returns a descriptive error string naming the offending kind, or
    ``None`` if valid.
    """
    for stmt in statements:
        if not _targets_workflow_node(stmt.get("actions", [])):
            continue
        conditions = stmt.get("conditions") or {}
        for key in ("resource_labels", "resource_labels_not"):
            labels = conditions.get(key) or {}
            kind = labels.get(NODE_KIND_LABEL)
            if kind is None:
                continue
            if not isinstance(kind, str) or not is_known_node_kind(kind):
                known = ", ".join(sorted(NODE_KINDS))
                return f"Unknown node kind '{kind}' for resource type '{NODE_RESOURCE_TYPE}'. Registered kinds: {known}"
    return None
