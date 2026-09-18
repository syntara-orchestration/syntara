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


def _triggers_by_id(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for trigger in definition.get("triggers") or []:
        if isinstance(trigger, dict) and trigger.get("id") is not None:
            mapping[str(trigger["id"])] = trigger
    return mapping


def _item_ids(items: list[Any]) -> set[str]:
    ids: set[str] = set()
    for item in items:
        if isinstance(item, dict) and item.get("id") is not None:
            ids.add(str(item["id"]))
    return ids


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


def _removal_permission_errors(
    previous_items: dict[str, dict[str, Any]],
    current_ids: set[str],
    permissions: dict[str, NodeTypeAccess],
    *,
    kind: str,
) -> list[str]:
    errors: list[str] = []
    for item_id, item in previous_items.items():
        if item_id in current_ids:
            continue
        item_type = str(item.get("type", ""))
        access = permissions.get(item_type)
        if access is None or not access.read or not access.write:
            errors.append(f"{kind} '{item_id}' ({item_type}) cannot be removed with your permissions")
    return errors


def _restore_read_denied_items(
    items: list[Any],
    previous_items: dict[str, dict[str, Any]],
    permissions: dict[str, NodeTypeAccess],
    *,
    kind: str,
    previous_definition: dict[str, Any] | None,
) -> tuple[list[Any], list[str]]:
    """Restore prior bodies for read-denied items; collect add errors for new ones."""
    errors: list[str] = []
    restored: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            restored.append(item)
            continue
        item_type = str(item.get("type", ""))
        item_id = str(item.get("id", item_type))
        access = permissions.get(item_type)
        if access is None:
            restored.append(item)
            continue
        if not access.read:
            if previous_definition is not None and item_id in previous_items:
                restored.append(copy.deepcopy(previous_items[item_id]))
            else:
                errors.append(f"{kind} '{item_id}' uses type '{item_type}' which you are not allowed to read")
                restored.append(item)
            continue
        if not access.write:
            if previous_definition is None or item_id not in previous_items:
                errors.append(f"{kind} '{item_id}' ({item_type}) cannot be added with your permissions")
            elif previous_items[item_id] != item:
                errors.append(f"{kind} '{item_id}' ({item_type}) is read-only for your account")
        restored.append(item)
    return restored, errors


def _node_permission_errors(
    nodes: list[Any],
    permissions: dict[str, NodeTypeAccess],
    previous_nodes: dict[str, dict[str, Any]],
    previous_definition: dict[str, Any] | None,
) -> tuple[list[Any], list[str]]:
    return _restore_read_denied_items(
        nodes,
        previous_nodes,
        permissions,
        kind="Node",
        previous_definition=previous_definition,
    )


def _trigger_permission_errors(
    triggers: list[Any],
    permissions: dict[str, NodeTypeAccess],
    previous_triggers: dict[str, dict[str, Any]],
    previous_definition: dict[str, Any] | None,
) -> tuple[list[Any], list[str]]:
    return _restore_read_denied_items(
        triggers,
        previous_triggers,
        permissions,
        kind="Trigger",
        previous_definition=previous_definition,
    )


async def validate_workflow_definition_node_permissions(
    db: AsyncSession,
    evaluator: AuthzEvaluator,
    user: User,
    *,
    project_id: UUID,
    workflow_definition: dict[str, Any],
    previous_definition: dict[str, Any] | None = None,
) -> list[str]:
    """Return human-readable errors when the user violates node-type permissions.

    Mutates *workflow_definition* in place to restore full prior bodies for any
    read-denied nodes/triggers that remain (so redacted stubs are not persisted).
    """
    node_types = iter_definition_node_types(workflow_definition)
    if previous_definition:
        node_types |= iter_definition_node_types(previous_definition)

    permissions = await resolve_node_type_permissions(
        db,
        evaluator,
        user,
        project_id=project_id,
        node_types=node_types,
    )
    previous_nodes = _nodes_by_id(previous_definition) if previous_definition else {}
    previous_triggers = _triggers_by_id(previous_definition) if previous_definition else {}

    submitted_nodes = list(workflow_definition.get("nodes") or [])
    submitted_triggers = list(workflow_definition.get("triggers") or [])

    errors = _removal_permission_errors(
        previous_nodes,
        _item_ids(submitted_nodes),
        permissions,
        kind="Node",
    )
    errors.extend(
        _removal_permission_errors(
            previous_triggers,
            _item_ids(submitted_triggers),
            permissions,
            kind="Trigger",
        )
    )

    restored_nodes, node_errors = _node_permission_errors(
        submitted_nodes,
        permissions,
        previous_nodes,
        previous_definition,
    )
    restored_triggers, trigger_errors = _trigger_permission_errors(
        submitted_triggers,
        permissions,
        previous_triggers,
        previous_definition,
    )
    errors.extend(node_errors)
    errors.extend(trigger_errors)

    workflow_definition["nodes"] = restored_nodes
    workflow_definition["triggers"] = restored_triggers
    return errors
