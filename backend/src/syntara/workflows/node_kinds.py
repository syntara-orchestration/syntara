"""Declarative registry of workflow node kinds (ANSTRAT-1750).

Single source of truth for *which node kinds exist* and what the
authorization layer may say about each of them.  Consumed by:

- the authz resource-actions registry, which exposes the ``workflow_node``
  resource type and marks it project-eligible;
- policy validation, which checks the ``kind`` label on ``workflow_node``
  statements against this registry;
- the node-kind kill switch and the builder node map.

Node kinds are not rows: the workflow definition is a JSONB blob and a
node's kind is an attribute of that blob.  The permission subject is the
``workflow_node`` resource type with the node kind carried as the ``kind``
label on the authorization input.

Categories decide which actions may be *denied* for a kind:

- ``trigger`` kinds may be denied for ``write`` (introducing the kind into a
  workflow) but never for ``execute`` -- a trigger starts the run, and whose
  permissions a run uses is decided at launch, not per trigger.
- ``flow_control`` kinds are never deniable; denying ``condition`` or the
  permission check node would break denial handling itself.
- ``action`` kinds may be denied for both ``write`` and ``execute``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

NODE_RESOURCE_TYPE = "workflow_node"
"""Resource type under which node kinds are authorized."""

NODE_KIND_LABEL = "kind"
"""Label key carrying the node kind on a ``workflow_node`` authorization input."""

NODE_ACTION_WRITE = "write"
NODE_ACTION_EXECUTE = "execute"
NODE_ACTIONS: frozenset[str] = frozenset({NODE_ACTION_WRITE, NODE_ACTION_EXECUTE})
"""Every action defined for the ``workflow_node`` resource type."""


class NodeKindCategory(StrEnum):
    """Coarse grouping that decides which actions may be denied for a kind."""

    TRIGGER = "trigger"
    FLOW_CONTROL = "flow_control"
    ACTION = "action"


_DENIABLE_BY_CATEGORY: dict[NodeKindCategory, frozenset[str]] = {
    NodeKindCategory.TRIGGER: frozenset({NODE_ACTION_WRITE}),
    NodeKindCategory.FLOW_CONTROL: frozenset(),
    NodeKindCategory.ACTION: NODE_ACTIONS,
}


@dataclass(frozen=True)
class NodeKindInfo:
    """Canonical description of one node kind."""

    kind: str
    category: NodeKindCategory

    @property
    def deniable_actions(self) -> frozenset[str]:
        """Actions that a deny-effect policy may target for this kind."""
        return _DENIABLE_BY_CATEGORY[self.category]

    def is_deniable(self, action: str) -> bool:
        """Return ``True`` if *action* (or the ``*`` wildcard) may be denied for this kind."""
        if action == "*":
            return bool(self.deniable_actions)
        return action in self.deniable_actions


_CATEGORY_BY_TYPE: dict[NodeType, NodeKindCategory] = {
    NodeType.MANUAL_TRIGGER: NodeKindCategory.TRIGGER,
    NodeType.SCHEDULED_TRIGGER: NodeKindCategory.TRIGGER,
    NodeType.WEBHOOK_TRIGGER: NodeKindCategory.TRIGGER,
    NodeType.EDA_TRIGGER: NodeKindCategory.TRIGGER,
    NodeType.CONDITION: NodeKindCategory.FLOW_CONTROL,
    NodeType.CONVERGE: NodeKindCategory.FLOW_CONTROL,
    NodeType.LOOP: NodeKindCategory.FLOW_CONTROL,
    NodeType.SWITCH: NodeKindCategory.FLOW_CONTROL,
    NodeType.WAIT: NodeKindCategory.FLOW_CONTROL,
    NodeType.PERMISSION_CHECK: NodeKindCategory.FLOW_CONTROL,
    NodeType.AAP_JOB_TEMPLATE: NodeKindCategory.ACTION,
    NodeType.AAP_WORKFLOW_JOB_TEMPLATE: NodeKindCategory.ACTION,
    NodeType.AGENTIC: NodeKindCategory.ACTION,
    NodeType.APPROVAL: NodeKindCategory.ACTION,
    NodeType.HTTP_REQUEST: NodeKindCategory.ACTION,
    NodeType.INTERNAL_ACTIVITY: NodeKindCategory.ACTION,
    NodeType.MCP_TOOL: NodeKindCategory.ACTION,
    NodeType.SCRIPT: NodeKindCategory.ACTION,
}

NODE_KINDS: tuple[NodeKindInfo, ...] = tuple(
    NodeKindInfo(kind=node_type.value, category=_CATEGORY_BY_TYPE[node_type]) for node_type in NodeType
)
"""Every registered node kind, in ``NodeType`` declaration order."""

_KIND_MAP: dict[str, NodeKindInfo] = {info.kind: info for info in NODE_KINDS}


def get_node_kind(kind: str) -> NodeKindInfo | None:
    """Look up a node kind by its ``NodeType`` value, or ``None`` if unknown."""
    return _KIND_MAP.get(kind)


def all_node_kinds() -> tuple[NodeKindInfo, ...]:
    """Return every registered node kind."""
    return NODE_KINDS


def node_kinds_by_category(category: NodeKindCategory) -> tuple[NodeKindInfo, ...]:
    """Return the node kinds in *category*."""
    return tuple(info for info in NODE_KINDS if info.category == category)


def deniable_node_kinds(action: str) -> frozenset[str]:
    """Return the kinds for which *action* may be denied."""
    return frozenset(info.kind for info in NODE_KINDS if info.is_deniable(action))


def node_kind_action_pairs() -> frozenset[tuple[str, str]]:
    """Return the ``(resource_type, action)`` pairs contributed to the authz registry."""
    return frozenset((NODE_RESOURCE_TYPE, action) for action in NODE_ACTIONS)


def _node_actions_in(actions: list[str]) -> list[str]:
    """Return the node actions (``write``, ``execute`` or ``*``) referenced by *actions*."""
    found: list[str] = []
    for action_str in actions:
        resource_type, _, action = action_str.partition(":")
        if resource_type == NODE_RESOURCE_TYPE and action:
            found.append(action)
    return found


def validate_node_kind_statements(statements: list[dict[str, Any]]) -> str | None:
    """Validate the ``kind`` label on ``workflow_node`` policy statements.

    Labels are free-form everywhere else in the system; for node kinds a
    typo would silently match nothing, so the value is checked against the
    registry.  For deny-effect statements the targeted action must also be
    deniable for that kind (triggers: write only; flow control: never).

    Returns a descriptive error string, or ``None`` if valid.
    """
    for stmt in statements:
        node_actions = _node_actions_in(stmt.get("actions", []))
        if not node_actions:
            continue
        conditions = stmt.get("conditions") or {}
        resource_labels = conditions.get("resource_labels") or {}
        kind = resource_labels.get(NODE_KIND_LABEL)
        if kind is None:
            continue
        info = get_node_kind(kind)
        if info is None:
            known = ", ".join(sorted(_KIND_MAP))
            return f"Unknown node kind '{kind}'. Registered kinds: {known}"
        if stmt.get("effect") != "deny":
            continue
        for action in node_actions:
            if not info.is_deniable(action):
                if not info.deniable_actions:
                    return f"Node kind '{kind}' ({info.category.value}) cannot be denied"
                allowed = ", ".join(sorted(info.deniable_actions))
                return (
                    f"Action '{action}' cannot be denied for node kind '{kind}' "
                    f"({info.category.value}); deniable: {allowed}"
                )
    return None
