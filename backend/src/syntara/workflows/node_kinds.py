"""Step-type identifiers and labels for authoring policies.

Grantable ``kind`` values on the ``step_type:write`` resource are the
authoring/palette ``NodeType`` values. System-only types such as
``internal_activity`` are excluded so they cannot be granted via policy.
Registration does not enforce permissions on workflow writes.
"""

from typing import Any

from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

NODE_RESOURCE_TYPE = "step_type"
NODE_KIND_LABEL = "kind"
NODE_ACTION_WRITE = "write"
# System-only node types are not grantable via authoring policies.
_NON_GRANTABLE_NODE_KINDS: frozenset[str] = frozenset({NodeType.INTERNAL_ACTIVITY.value})
NODE_KINDS: frozenset[str] = frozenset(
    node_type.value for node_type in NodeType if node_type.value not in _NON_GRANTABLE_NODE_KINDS
)
NODE_KIND_DISPLAY_LABELS: dict[str, str] = {
    "manual_trigger": "Manual trigger",
    "scheduled_trigger": "Schedule trigger",
    "webhook_trigger": "Webhook trigger",
    "eda_trigger": "Event-Driven Ansible trigger",
    "condition": "Conditional",
    "converge": "Converge",
    "loop": "Loop",
    "switch": "Switch",
    "wait": "Wait",
    "aap_job_template": "AAP Job Template",
    "aap_workflow_job_template": "AAP Workflow Template",
    "agentic": "Task Agent",
    "approval": "Approval",
    "http_request": "REST API",
    "script": "Script",
}


def node_kind_display_label(kind: str) -> str:
    """Human-readable label for a step type; falls back to title-cased kind."""
    return NODE_KIND_DISPLAY_LABELS.get(kind, kind.replace("_", " ").title())


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
