"""Workflow node-type permission inheritance and workflow definition redaction."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from syntara.authz.engine import AuthzRequest, authorize
from syntara.authz.models.project import Project
from syntara.authz.resolver import resolve_effective_policies, resolve_user_groups
from syntara.authz.workflow_node_type_catalog import (
    NODE_TYPE_ACTIONS,
    WORKFLOW_NODE_TYPE_RESOURCE,
    catalog_display_name,
    load_node_type_catalog_entries,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.authz.evaluator import AuthzEvaluator
    from syntara.core.models import User

PERMISSION_REDACTED_KEY = "_permission_redacted"

_WORKFLOW_ACTION_BY_NODE_ACTION: dict[str, tuple[str, str]] = {
    "read": ("workflow", "read"),
    "write": ("workflow", "update"),
    "execute": ("execution", "run"),
}


@dataclass(frozen=True)
class NodeTypeAccess:
    """Effective node-type permissions for one catalog type."""

    read: bool
    write: bool
    execute: bool


def iter_definition_node_types(workflow_definition: dict[str, Any]) -> set[str]:
    """Collect node type ids from a v2 workflow definition dict."""
    types: set[str] = set()
    for node in workflow_definition.get("nodes") or []:
        node_type = node.get("type")
        if isinstance(node_type, str) and node_type:
            types.add(node_type)
    for trigger in workflow_definition.get("triggers") or []:
        trigger_type = trigger.get("type")
        if isinstance(trigger_type, str) and trigger_type:
            types.add(trigger_type)
    return types


async def _resolve_project_name(db: AsyncSession, project_id: UUID) -> str:
    project = await db.get(Project, project_id)
    if project is None:
        return ""
    return project.name


async def _workflow_action_allowed(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    project_name: str,
    node_action: str,
) -> bool:
    resource_type, workflow_action = _WORKFLOW_ACTION_BY_NODE_ACTION[node_action]
    result = await authorize(
        db,
        evaluator,
        AuthzRequest(
            user_id=user.id,
            action=workflow_action,
            resource_type=resource_type,
            resource_id="",
            resource_project=project_name,
            user_labels=user.labels,
            user_metadata=user.authz_metadata,
        ),
    )
    return result.allowed and not result.denied


async def _has_explicit_node_type_deny(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    project_name: str,
    node_type: str,
    node_action: str,
) -> bool:
    effective = await resolve_effective_policies(db, user.id)
    deny_policies = [p for p in effective if p.get("effect") == "deny"]
    if not deny_policies:
        return False

    groups = await resolve_user_groups(db, user.id)
    authz_input: dict[str, Any] = {
        "user": {
            "id": str(user.id),
            "metadata": user.authz_metadata,
            "labels": user.labels,
        },
        "action": node_action,
        "resource": {
            "type": WORKFLOW_NODE_TYPE_RESOURCE,
            "id": node_type,
            "project": project_name,
            "any_project": False,
            "metadata": {"node_type": node_type},
            "labels": {},
        },
        "groups": groups,
        "effective_policies": deny_policies,
    }
    opa_result = evaluator.evaluate(authz_input)
    return bool(opa_result.get("deny"))


def _nodes_by_id(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for node in definition.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") is not None:
            mapping[str(node["id"])] = node
    return mapping


async def is_node_type_action_allowed(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    *,
    project_id: UUID,
    node_type: str,
    action: str,
) -> bool:
    """Return True when the user may perform *action* on *node_type* (inheritance + deny)."""
    if action not in NODE_TYPE_ACTIONS:
        msg = f"Unsupported node-type action: {action}"
        raise ValueError(msg)
    project_name = await _resolve_project_name(db, project_id)
    inherited = await _workflow_action_allowed(db, evaluator, user, project_name, action)
    if not inherited:
        return False
    return not await _has_explicit_node_type_deny(db, evaluator, user, project_name, node_type, action)


async def resolve_node_type_permissions(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    *,
    project_id: UUID,
    node_types: set[str] | None = None,
) -> dict[str, NodeTypeAccess]:
    """Resolve effective read/write/execute for each requested node type."""
    types = node_types if node_types is not None else {t for t, _ in load_node_type_catalog_entries()}
    result: dict[str, NodeTypeAccess] = {}
    for node_type in types:
        read = await is_node_type_action_allowed(
            db, evaluator, user, project_id=project_id, node_type=node_type, action="read"
        )
        write = await is_node_type_action_allowed(
            db, evaluator, user, project_id=project_id, node_type=node_type, action="write"
        )
        execute = await is_node_type_action_allowed(
            db, evaluator, user, project_id=project_id, node_type=node_type, action="execute"
        )
        result[node_type] = NodeTypeAccess(read=read, write=write, execute=execute)
    return result


def _redact_node(node: dict[str, Any], node_type: str) -> dict[str, Any]:
    redacted = {
        "id": node.get("id"),
        "type": node_type,
        "name": catalog_display_name(node_type),
        PERMISSION_REDACTED_KEY: True,
    }
    if node.get("position") is not None:
        redacted["position"] = copy.deepcopy(node["position"])
    return redacted


async def filter_workflow_definition_for_user(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    *,
    project_id: UUID,
    workflow_definition: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of the definition with nodes redacted when read is denied."""
    if not workflow_definition:
        return workflow_definition
    filtered = copy.deepcopy(workflow_definition)
    node_types = iter_definition_node_types(filtered)
    permissions = await resolve_node_type_permissions(db, evaluator, user, project_id=project_id, node_types=node_types)

    nodes: list[Any] = []
    for node in filtered.get("nodes") or []:
        if not isinstance(node, dict):
            nodes.append(node)
            continue
        node_type = str(node.get("type", ""))
        access = permissions.get(node_type)
        if access is not None and not access.read:
            nodes.append(_redact_node(node, node_type))
        else:
            nodes.append(node)
    filtered["nodes"] = nodes

    triggers: list[Any] = []
    for trigger in filtered.get("triggers") or []:
        if not isinstance(trigger, dict):
            triggers.append(trigger)
            continue
        trigger_type = str(trigger.get("type", ""))
        access = permissions.get(trigger_type)
        if access is not None and not access.read:
            triggers.append(_redact_node(trigger, trigger_type))
        else:
            triggers.append(trigger)
    filtered["triggers"] = triggers
    return filtered


def _node_permission_errors(
    nodes: list[Any],
    permissions: dict[str, NodeTypeAccess],
    previous_nodes: dict[str, dict[str, Any]],
    previous_definition: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", ""))
        node_id = str(node.get("id", node_type))
        access = permissions.get(node_type)
        if access is None:
            continue
        if not access.read:
            errors.append(f"Node '{node_id}' uses type '{node_type}' which you are not allowed to read")
            continue
        if not access.write:
            if previous_definition is None or node_id not in previous_nodes:
                errors.append(f"Node '{node_id}' ({node_type}) cannot be added with your permissions")
            elif previous_nodes[node_id] != node:
                errors.append(f"Node '{node_id}' ({node_type}) is read-only for your account")
    return errors


def _trigger_permission_errors(triggers: list[Any], permissions: dict[str, NodeTypeAccess]) -> list[str]:
    errors: list[str] = []
    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue
        trigger_type = str(trigger.get("type", ""))
        trigger_id = str(trigger.get("id", trigger_type))
        access = permissions.get(trigger_type)
        if access is None:
            continue
        if not access.read:
            errors.append(f"Trigger '{trigger_id}' uses type '{trigger_type}' which you are not allowed to read")
        elif not access.write:
            errors.append(f"Trigger '{trigger_id}' ({trigger_type}) is read-only for your account")
    return errors


async def validate_workflow_definition_node_permissions(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    *,
    project_id: UUID,
    workflow_definition: dict[str, Any],
    previous_definition: dict[str, Any] | None = None,
) -> list[str]:
    """Return human-readable errors when the user violates node-type permissions."""
    permissions = await resolve_node_type_permissions(
        db,
        evaluator,
        user,
        project_id=project_id,
        node_types=iter_definition_node_types(workflow_definition),
    )
    previous_nodes = _nodes_by_id(previous_definition) if previous_definition else {}
    errors = _node_permission_errors(
        workflow_definition.get("nodes") or [],
        permissions,
        previous_nodes,
        previous_definition,
    )
    errors.extend(_trigger_permission_errors(workflow_definition.get("triggers") or [], permissions))
    return errors
