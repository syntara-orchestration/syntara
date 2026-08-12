"""Policy resolver: loads user's effective policies from the database.

Resolution chain: user → groups (GroupMembership) → role assignments
→ role names → policies (builtins from code, custom from DB).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import structlog
from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.project import Project
from syntara.authz.models.role import Role
from syntara.authz.role_conventions import (
    get_builtin_role,
    is_builtin_policy,
    resolve_builtin_policy_statements,
)
from syntara.core.models.group import Group, user_groups

logger = structlog.stdlib.get_logger(__name__)

AUTHENTICATED_GROUP_NAME = "authenticated"


def _action_matches(stmt: dict[str, Any], action_accept: set[str] | None) -> bool:
    """Return True if the statement should be included given the action filter."""
    if not action_accept or stmt.get("effect") == "deny":
        return True
    return bool(action_accept.intersection(stmt.get("actions", ())))


async def _resolve_roles_to_policies(
    db: AsyncSession,
    role_names: list[str],
    seen: set[str],
    result: list[dict[str, Any]],
    project: str = "",
    project_id: UUID | None = None,
    action_accept: set[str] | None = None,
) -> None:
    """Resolve role names to policy statements and add to result.

    Built-in roles are resolved entirely from code (zero DB queries).
    Custom roles are resolved via the roles table + role_policies join.

    When *action_accept* is provided, only statements whose actions
    intersect with the accept set (or that have deny effect) are included.
    """
    if not role_names:
        return

    custom_role_names: list[str] = []
    for rn in role_names:
        builtin = get_builtin_role(rn)
        if builtin:
            _add_builtin_role_statements(rn, seen, result, project, action_accept)
        else:
            custom_role_names.append(rn)

    if custom_role_names:
        await _resolve_custom_roles(db, custom_role_names, seen, result, project, project_id, action_accept)


def _scope_entry_to_project(entry: dict[str, Any], project: str) -> dict[str, Any]:
    """Return a copy of *entry* scoped to *project*."""
    if entry.get("scope") == "self":
        return {**entry, "project": project}
    return {**entry, "scope": "project", "project": project}


def _add_builtin_role_statements(
    role_name: str,
    seen: set[str],
    result: list[dict[str, Any]],
    project: str,
    action_accept: set[str] | None = None,
) -> None:
    """Add statements for a built-in role from code registry."""
    from syntara.authz.role_conventions import builtin_role_policy_names  # noqa: PLC0415

    for policy_name in builtin_role_policy_names(role_name):
        for stmt in resolve_builtin_policy_statements(policy_name):
            if not _action_matches(stmt, action_accept):
                continue
            entry = {**stmt, "name": policy_name}
            name = f"{policy_name}@{project}" if project else policy_name
            if project:
                entry = _scope_entry_to_project(entry, project)
            if name not in seen:
                seen.add(name)
                result.append(entry)


async def _load_custom_policies(
    db: AsyncSession,
    names: list[str],
    project_id: UUID | None,
) -> dict[str, Policy]:
    """Load custom policies by name, scoped to *project_id* or global.

    When both a project-scoped and global policy share a name, the
    project-scoped policy takes precedence.
    """
    if not names:
        return {}
    policies_result = await db.exec(
        select(Policy).where(
            Policy.name.in_(names),  # type: ignore[attr-defined]
            or_(Policy.project_id == project_id, Policy.project_id.is_(None)),  # type: ignore[union-attr]
        )
    )
    result: dict[str, Policy] = {}
    for p in policies_result.all():
        if p.name not in result or p.project_id is not None:
            result[p.name] = p
    return result


async def _resolve_custom_roles(
    db: AsyncSession,
    role_names: list[str],
    seen: set[str],
    result: list[dict[str, Any]],
    project: str,
    project_id: UUID | None = None,
    action_accept: set[str] | None = None,
) -> None:
    """Resolve custom (non-builtin) roles via DB.

    Reads ``policy_names`` from each Role, then resolves each name
    against builtins first, falling back to the policies table.
    """
    roles_result = await db.exec(
        select(Role).where(
            Role.name.in_(role_names),  # type: ignore[attr-defined]
            or_(Role.project_id == project_id, Role.project_id.is_(None)),  # type: ignore[union-attr]
        )
    )
    roles = list(roles_result.all())
    if not roles:
        return

    all_policy_names: set[str] = set()
    for role in roles:
        all_policy_names.update(role.policy_names)

    custom_policy_names = [n for n in all_policy_names if not is_builtin_policy(n)]
    custom_policies = await _load_custom_policies(db, custom_policy_names, project_id)

    for role in roles:
        _expand_role_policies(role, custom_policies, seen, result, project, action_accept)


def _expand_role_policies(
    role: Role,
    custom_policies: dict[str, Policy],
    seen: set[str],
    result: list[dict[str, Any]],
    project: str,
    action_accept: set[str] | None,
) -> None:
    """Expand a single role's policy names into statement entries."""
    for pn in role.policy_names:
        stmts, fallback = _resolve_policy_statements(pn, custom_policies)
        for stmt in stmts:
            if not _action_matches(stmt, action_accept):
                continue
            _add_stmt(stmt, fallback, seen, result, project)


def _resolve_policy_statements(
    policy_name: str,
    custom_policies: dict[str, Policy],
) -> tuple[Sequence[dict[str, Any]], str]:
    """Return (statements, fallback_name) for a policy name."""
    if is_builtin_policy(policy_name):
        return resolve_builtin_policy_statements(policy_name), policy_name
    if policy_name in custom_policies:
        return custom_policies[policy_name].to_statement_dicts(), ""
    return (), ""


def _add_stmt(
    stmt: dict[str, Any],
    fallback_name: str,
    seen: set[str],
    result: list[dict[str, Any]],
    project: str,
) -> None:
    name = stmt.get("name", fallback_name)
    entry = _scope_entry_to_project(stmt, project) if project else stmt
    name = f"{name}@{project}" if project else name
    if name not in seen:
        seen.add(name)
        result.append(entry)


async def get_user_group_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """Return group IDs for a user, including the implicit 'authenticated' group."""
    result = await db.exec(
        select(user_groups.c.group_id)
        .join(Group, Group.id == user_groups.c.group_id)  # type: ignore[arg-type]
        .where(
            user_groups.c.user_id == user_id,
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    group_ids = list(result.all())

    auth_group_result = await db.exec(
        select(Group).where(
            Group.name == AUTHENTICATED_GROUP_NAME,
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    auth_group = auth_group_result.first()
    if auth_group and auth_group.id not in group_ids:
        group_ids.append(auth_group.id)

    return group_ids


def _partition_assignments(
    assignments: Sequence[RoleAssignment],
    project_roles: dict[UUID, list[str]],
) -> tuple[list[str], dict[UUID, list[str]]]:
    """Split assignments into global role names and per-project role names."""
    global_names: list[str] = []
    for a in assignments:
        if a.project_id is None:
            global_names.append(a.role_name)
        else:
            project_roles.setdefault(a.project_id, []).append(a.role_name)
    return global_names, project_roles


async def resolve_effective_policies(
    db: AsyncSession,
    principal_id: UUID,
    *,
    action_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve effective policies for a principal (user or service account).

    When *action_filter* is provided (e.g. ``"workflow:read"``), only
    project-scoped policies whose actions include the requested action (or
    its wildcard ``resource:*``) are expanded.  Global and deny-effect
    policies are always included.  This avoids O(projects x policies_per_role)
    expansion for users with roles across many projects.

    When *action_filter* is ``None``, all policies are expanded (needed by
    introspection endpoints like ``what_can_i``).

    Resolution order:
    1. Global: principal → groups (including "authenticated") → roles → policies
    2. Global: principal → direct role assignments → policies
    3. Project-scoped: principal + group assignments with project_id set → policies
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []

    group_ids = await get_user_group_ids(db, principal_id)

    project_role_names: dict[UUID, list[str]] = {}

    if group_ids:
        group_assignments = await db.exec(
            select(RoleAssignment).where(
                RoleAssignment.group_id.in_(group_ids),  # type: ignore[union-attr]
            )
        )
        global_group, project_role_names = _partition_assignments(group_assignments.all(), project_role_names)
        await _resolve_roles_to_policies(db, global_group, seen, result)

    direct_assignments = await db.exec(
        select(RoleAssignment).where(
            RoleAssignment.principal_id == principal_id,
        )
    )
    direct_global, project_role_names = _partition_assignments(direct_assignments.all(), project_role_names)
    await _resolve_roles_to_policies(db, direct_global, seen, result)

    if project_role_names:
        projects_result = await db.exec(
            select(Project).where(
                Project.id.in_(list(project_role_names.keys())),  # type: ignore[attr-defined]
                Project.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        project_map = {p.id: p.name for p in projects_result.all()}

        if action_filter:
            resource_type, _, _ = action_filter.partition(":")
            wildcard = f"{resource_type}:*"
            accept = {action_filter, wildcard}
        else:
            accept = None

        for pid, names in project_role_names.items():
            project_name = project_map.get(pid, str(pid))
            await _resolve_roles_to_policies(
                db,
                names,
                seen,
                result,
                project=project_name,
                project_id=pid,
                action_accept=accept,
            )

    return result


async def resolve_user_groups(
    db: AsyncSession,
    user_id: UUID,
) -> list[dict[str, Any]]:
    """Resolve group memberships for a user.

    Returns group info in the format expected by the evaluator:
    [{"name": "group-name", "id": "uuid", "labels": {"key": "value"}}]
    """
    group_ids = await get_user_group_ids(db, user_id)

    if not group_ids:
        return []

    groups_result = await db.exec(
        select(Group).where(
            Group.id.in_(group_ids),  # type: ignore[attr-defined]
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return [{"name": g.name, "id": str(g.id), "labels": g.labels} for g in groups_result.all()]
