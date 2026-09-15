"""Built-in deny-template policies for workflow node-type permissioning."""

from __future__ import annotations

from syntara.authz.role_conventions import PolicyInfo
from syntara.authz.workflow_node_type_catalog import (
    NODE_TYPE_ACTIONS,
    WORKFLOW_NODE_TYPE_RESOURCE,
    load_node_type_catalog_entries,
)


def _node_type_policy_name(node_type: str, action: str) -> str:
    return f"{WORKFLOW_NODE_TYPE_RESOURCE}:{node_type}:{action}:any"


def generate_workflow_node_type_policies() -> list[PolicyInfo]:
    """Build deny-template builtin policies for every catalog node type and action."""
    return [
        PolicyInfo(
            resource=WORKFLOW_NODE_TYPE_RESOURCE,
            action=action,
            scope="any",
            roles=(),
            effect="deny",
            conditions={"resource_metadata": {"node_type": node_type}},
            policy_name_override=_node_type_policy_name(node_type, action),
            node_type_label=display_name,
        )
        for node_type, display_name in load_node_type_catalog_entries()
        for action in NODE_TYPE_ACTIONS
    ]


WORKFLOW_NODE_TYPE_POLICIES: list[PolicyInfo] = generate_workflow_node_type_policies()
