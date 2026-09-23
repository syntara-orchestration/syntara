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
- ``flow_control`` kinds are never deniable; denying them would break workflow
  routing semantics.
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
class NodeAttributeInfo:
    """One node parameter exposed as an authorization resource label."""

    name: str
    allowed_values: frozenset[str] | None = None


@dataclass(frozen=True)
class NodeKindInfo:
    """Canonical description of one node kind."""

    kind: str
    category: NodeKindCategory
    attributes: tuple[NodeAttributeInfo, ...] = ()

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
    NodeType.AAP_JOB_TEMPLATE: NodeKindCategory.ACTION,
    NodeType.AAP_WORKFLOW_JOB_TEMPLATE: NodeKindCategory.ACTION,
    NodeType.AGENTIC: NodeKindCategory.ACTION,
    NodeType.APPROVAL: NodeKindCategory.ACTION,
    NodeType.HTTP_REQUEST: NodeKindCategory.ACTION,
    NodeType.INTERNAL_ACTIVITY: NodeKindCategory.ACTION,
    NodeType.MCP_TOOL: NodeKindCategory.ACTION,
    NodeType.SCRIPT: NodeKindCategory.ACTION,
}

_ATTRIBUTES_BY_KIND: dict[str, tuple[NodeAttributeInfo, ...]] = {
    "script": (NodeAttributeInfo("language", frozenset({"python", "bash"})),),
    "http_request": (NodeAttributeInfo("method", frozenset({"get", "post", "put", "patch", "delete"})),),
    "mcp_tool": (NodeAttributeInfo("tool_name"), NodeAttributeInfo("integration_id")),
    "aap_job_template": (NodeAttributeInfo("job_template_name"), NodeAttributeInfo("integration_id")),
    "aap_workflow_job_template": (
        NodeAttributeInfo("workflow_job_template_name"),
        NodeAttributeInfo("integration_id"),
    ),
    "agentic": (NodeAttributeInfo("model"),),
    "internal_activity": (
        NodeAttributeInfo(
            "activity",
            frozenset(
                {
                    "document_conversion",
                    "invocation_execution",
                    "integration_health_check",
                    "integration_resource_discovery",
                }
            ),
        ),
    ),
}

NODE_KINDS: tuple[NodeKindInfo, ...] = tuple(
    NodeKindInfo(
        kind=node_type.value,
        category=_CATEGORY_BY_TYPE[node_type],
        attributes=_ATTRIBUTES_BY_KIND.get(node_type.value, ()),
    )
    for node_type in NodeType
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


def normalise_attribute_value(value: object) -> str | None:
    """Return the normalized label value, or ``None`` when it must be omitted."""
    if not isinstance(value, str) or "{{" in value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def node_labels(node: dict[str, Any]) -> dict[str, str]:
    """Derive the authorization labels for a workflow node dictionary."""
    kind = node.get("type")
    if not isinstance(kind, str) or not kind:
        return {}
    labels = {NODE_KIND_LABEL: kind}
    info = get_node_kind(kind)
    parameters = node.get("parameters")
    if info is None or not isinstance(parameters, dict):
        return labels
    for attribute in info.attributes:
        value = normalise_attribute_value(parameters.get(attribute.name))
        if value is not None and (attribute.allowed_values is None or value in attribute.allowed_values):
            labels[attribute.name] = value
    return labels


def _validate_attribute_labels(labels: dict[str, Any]) -> str | None:  # noqa: PLR0911
    """Validate one positive or negative resource-label condition."""
    attribute_names = set(labels) - {NODE_KIND_LABEL}
    kind = labels.get(NODE_KIND_LABEL)
    if attribute_names and kind is None:
        return "Node attribute labels require a 'kind' label"
    if kind is None:
        return None
    info = get_node_kind(kind)
    if info is None:
        known = ", ".join(sorted(_KIND_MAP))
        return f"Unknown node kind '{kind}'. Registered kinds: {known}"
    attributes = {attribute.name: attribute for attribute in info.attributes}
    for name in sorted(attribute_names):
        attribute = attributes.get(name)
        allowed_names = ", ".join(sorted(attributes)) or "none"
        if attribute is None:
            return f"Unknown attribute '{name}' for node kind '{kind}'. Allowed: {allowed_names}"
        value = labels[name]
        normalized = normalise_attribute_value(value)
        if normalized is None or normalized != value:
            return f"Attribute '{name}' for node kind '{kind}' must be a non-empty normalized string"
        if attribute.allowed_values is not None and value not in attribute.allowed_values:
            allowed_values = ", ".join(sorted(attribute.allowed_values))
            return f"Invalid value '{value}' for attribute '{name}' on node kind '{kind}'. Allowed: {allowed_values}"
    return None


def _node_actions_in(actions: list[str]) -> list[str]:
    """Return the node actions (``write``, ``execute`` or ``*``) referenced by *actions*."""
    found: list[str] = []
    for action_str in actions:
        resource_type, _, action = action_str.partition(":")
        if resource_type == NODE_RESOURCE_TYPE and action:
            found.append(action)
    return found


def validate_node_kind_statements(statements: list[dict[str, Any]]) -> str | None:  # noqa: C901
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
        error = _validate_attribute_labels(resource_labels)
        if error:
            return error
        resource_labels_not = conditions.get("resource_labels_not") or {}
        error = _validate_attribute_labels(resource_labels_not)
        if error:
            return error
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
