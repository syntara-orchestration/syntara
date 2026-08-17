"""Central registries for built-in policies and roles.

``PolicyInfo`` captures ``(resource, action, scope)`` plus the built-in
roles the policy is assigned to.  ``BUILTIN_POLICIES`` is the single
source of truth for all built-in policies.

``RoleInfo`` describes a system role; ``BUILTIN_ROLES`` is the single
source of truth for which roles exist and which policies they include.

Built-in roles and policies are **not** stored in the database.  They
exist only in this module and are resolved at runtime by the policy
resolver and merged into API list/get responses by the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid5

_BUILTIN_NS = UUID("a3c1f8d0-7e2b-4f5a-9c6d-1b8e3f0a2d4c")


@dataclass(frozen=True)
class PolicyInfo:
    """Canonical description of one built-in policy."""

    resource: str
    action: str
    scope: str = "any"
    roles: tuple[str, ...] = field(default=(), compare=False, hash=False)

    @property
    def name(self) -> str:
        """Canonical 3-part policy name."""
        return f"{self.resource}:{self.action}:{self.scope}"

    @property
    def description(self) -> str:
        """Human-readable description."""
        scope_label = "own" if self.scope == "self" else self.scope
        action_label = self.action.capitalize()
        return f"{action_label} {scope_label} {self.resource}"

    @property
    def statements(self) -> list[dict[str, object]]:
        """Rego policy statement list."""
        return [
            {
                "effect": "allow",
                "actions": [f"{self.resource}:{self.action}"],
                "scope": self.scope,
            }
        ]

    @classmethod
    def from_name(cls, name: str) -> PolicyInfo:
        """Parse a canonical policy name (``resource:action:scope``) into a PolicyInfo."""
        parts = name.split(":")
        if len(parts) == 3:  # noqa: PLR2004
            return cls(resource=parts[0], action=parts[1], scope=parts[2])
        if len(parts) == 2:  # noqa: PLR2004
            return cls(resource=parts[0], action=parts[1])
        msg = f"Invalid policy name: {name!r}"
        raise ValueError(msg)


@dataclass(frozen=True)
class RoleInfo:
    """Canonical description of one system role."""

    name: str
    description: str
    is_builtin: bool = True
    scope: str = "system"


# ---------------------------------------------------------------------------
# Authoritative registry of ALL built-in policies.
#
# Each PolicyInfo declares which built-in roles receive the policy via
# the ``roles`` tuple.  The role→policy mapping is derived by inverting
# these declarations (see ``builtin_role_policy_names``).
# ---------------------------------------------------------------------------

BUILTIN_POLICIES: list[PolicyInfo] = [
    # -- self-scoped --
    PolicyInfo("user", "read", scope="self", roles=("admin", "authenticated")),
    PolicyInfo("user", "update", scope="self", roles=("admin", "authenticated")),
    # -- system-scoped (any) --
    # credentials
    PolicyInfo("credential", "read", roles=("admin", "auditor")),
    PolicyInfo("credential", "create", roles=("admin",)),
    PolicyInfo("credential", "update", roles=("admin",)),
    PolicyInfo("credential", "delete", roles=("admin",)),
    PolicyInfo("credential", "use", roles=("admin",)),
    # tools
    PolicyInfo("tool", "read", roles=("admin", "auditor", "user")),
    PolicyInfo("tool", "update", roles=("admin",)),
    # llm models
    PolicyInfo("llm_model", "read", roles=("admin", "auditor", "user")),
    PolicyInfo("llm_model", "update", roles=("admin",)),
    # integrations
    PolicyInfo("integration", "read", roles=("admin", "auditor", "user")),
    PolicyInfo("integration", "read-all", roles=("admin", "auditor")),
    PolicyInfo("integration", "create", roles=("admin",)),
    PolicyInfo("integration", "update", roles=("admin",)),
    PolicyInfo("integration", "delete", roles=("admin",)),
    PolicyInfo("integration", "discover", roles=("admin",)),
    PolicyInfo("integration", "validate", roles=("admin",)),
    PolicyInfo("integration", "refresh", roles=("admin",)),
    # workflows
    PolicyInfo("workflow", "read", roles=("admin", "auditor")),
    PolicyInfo("workflow", "create", roles=("admin",)),
    PolicyInfo("workflow", "update", roles=("admin",)),
    PolicyInfo("workflow", "delete", roles=("admin",)),
    # executions
    PolicyInfo("execution", "read", roles=("admin", "auditor")),
    PolicyInfo("execution", "run", roles=("admin",)),
    # approvals
    PolicyInfo("approval", "read", roles=("admin", "auditor")),
    PolicyInfo("approval", "decide", roles=("admin",)),
    PolicyInfo("approval", "create", roles=("admin",)),
    PolicyInfo("approval", "delete", roles=("admin",)),
    # projects
    PolicyInfo("project", "read", roles=("admin", "auditor")),
    PolicyInfo("project", "create", roles=("admin", "user")),
    PolicyInfo("project", "update", roles=("admin",)),
    PolicyInfo("project", "delete", roles=("admin",)),
    # role assignments
    PolicyInfo("role-assignment", "read", scope="self", roles=("admin", "auditor", "authenticated")),
    PolicyInfo("role-assignment", "read", roles=("admin", "auditor")),
    PolicyInfo("role-assignment", "assign", roles=("admin",)),
    PolicyInfo("role-assignment", "revoke", roles=("admin",)),
    # roles & policies (system-level admin)
    PolicyInfo("role", "create", roles=("admin",)),
    PolicyInfo("role", "read", roles=("admin", "auditor")),
    PolicyInfo("role", "update", roles=("admin",)),
    PolicyInfo("role", "delete", roles=("admin",)),
    PolicyInfo("policy", "create", roles=("admin",)),
    PolicyInfo("policy", "read", roles=("admin", "auditor")),
    PolicyInfo("policy", "update", roles=("admin",)),
    PolicyInfo("policy", "delete", roles=("admin",)),
    # users & groups
    PolicyInfo("user", "create", roles=("admin",)),
    PolicyInfo("user", "read", roles=("admin", "auditor")),
    PolicyInfo("user", "update", roles=("admin",)),
    PolicyInfo("user", "delete", roles=("admin",)),
    PolicyInfo("group", "create", roles=("admin",)),
    PolicyInfo("group", "read", roles=("admin", "auditor")),
    PolicyInfo("group", "update", roles=("admin",)),
    PolicyInfo("group", "delete", roles=("admin",)),
    PolicyInfo("group", "manage-members", roles=("admin",)),
    # user / group directory (lightweight lookup)
    PolicyInfo("user-directory", "read", roles=("admin", "auditor", "user")),
    PolicyInfo("group-directory", "read", roles=("admin", "auditor", "user")),
    # user identities (federated identity links)
    PolicyInfo("user_identity", "read", scope="self", roles=("admin", "authenticated")),
    PolicyInfo("user_identity", "read", roles=("admin",)),
    PolicyInfo("user_identity", "attach", roles=("admin",)),
    PolicyInfo("user_identity", "detach", scope="self", roles=("admin", "authenticated")),
    PolicyInfo("user_identity", "detach", roles=("admin",)),
    # identity providers
    PolicyInfo("identity-provider", "create", roles=("admin",)),
    PolicyInfo("identity-provider", "read", roles=("admin", "auditor")),
    PolicyInfo("identity-provider", "update", roles=("admin",)),
    PolicyInfo("identity-provider", "delete", roles=("admin",)),
    PolicyInfo("identity-provider", "test", roles=("admin",)),
    # settings
    PolicyInfo("setting", "read", roles=("admin", "auditor")),
    PolicyInfo("setting", "write", roles=("admin",)),
    # authz query
    PolicyInfo("authz", "query", roles=("admin",)),
    # admin revocation
    PolicyInfo("admin:revocation", "read", roles=("admin", "auditor")),
    PolicyInfo("admin:revocation", "execute", roles=("admin",)),
    # invocations
    PolicyInfo("invocation", "create", roles=("admin",)),
    PolicyInfo("invocation", "read", roles=("admin",)),
    PolicyInfo("invocation", "cancel", roles=("admin",)),
    # -- project-scoped --
    PolicyInfo("workflow", "create", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("workflow", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("workflow", "update", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("workflow", "delete", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("execution", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("execution", "run", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("integration", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("tool", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("llm_model", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("credential", "create", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("credential", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("credential", "update", scope="project", roles=("project-admin",)),
    PolicyInfo("credential", "update", scope="own", roles=("project-user",)),
    PolicyInfo("credential", "delete", scope="project", roles=("project-admin",)),
    PolicyInfo("credential", "use", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("approval", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("approval", "decide", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("approval", "delete", scope="project", roles=("project-admin",)),
    PolicyInfo("project", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("project", "update", scope="project", roles=("project-admin",)),
    PolicyInfo("project", "delete", scope="project", roles=("project-admin",)),
    PolicyInfo("role-assignment", "read", scope="project", roles=("project-admin",)),
    PolicyInfo("role-assignment", "assign", scope="project", roles=("project-admin",)),
    PolicyInfo("role-assignment", "revoke", scope="project", roles=("project-admin",)),
    PolicyInfo("role", "create", scope="project", roles=("project-admin",)),
    PolicyInfo("role", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("role", "update", scope="project", roles=("project-admin",)),
    PolicyInfo("role", "delete", scope="project", roles=("project-admin",)),
    PolicyInfo("policy", "create", scope="project", roles=("project-admin",)),
    PolicyInfo("policy", "read", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    PolicyInfo("policy", "update", scope="project", roles=("project-admin",)),
    PolicyInfo("policy", "delete", scope="project", roles=("project-admin",)),
    # -- files --
    PolicyInfo("files", "upload", roles=("admin", "user")),
    PolicyInfo("files", "download", roles=("admin", "user")),
    PolicyInfo("files", "upload", scope="project", roles=("project-admin", "project-user")),
    PolicyInfo("files", "download", scope="project", roles=("project-admin", "project-user", "project-auditor")),
    # -- service accounts --
    PolicyInfo("service_account", "create", roles=("admin",)),
    PolicyInfo("service_account", "read", roles=("admin", "auditor")),
    PolicyInfo("service_account", "update", roles=("admin",)),
    PolicyInfo("service_account", "delete", roles=("admin",)),
    PolicyInfo("service_account", "rotate_secret", roles=("admin",)),
    PolicyInfo("service_account", "disable", roles=("admin",)),
    PolicyInfo("service_account", "enable", roles=("admin",)),
    # -- service accounts (project-scoped) --
    PolicyInfo("service_account", "create", scope="project", roles=("project-admin",)),
    PolicyInfo("service_account", "read", scope="project", roles=("project-admin", "project-auditor")),
    PolicyInfo("service_account", "update", scope="project", roles=("project-admin",)),
    PolicyInfo("service_account", "delete", scope="project", roles=("project-admin",)),
    PolicyInfo("service_account", "rotate_secret", scope="project", roles=("project-admin",)),
    PolicyInfo("service_account", "disable", scope="project", roles=("project-admin",)),
    PolicyInfo("service_account", "enable", scope="project", roles=("project-admin",)),
]

BUILTIN_ROLES: list[RoleInfo] = [
    RoleInfo("admin", "Full access to all resources"),
    RoleInfo("auditor", "Read-only access with audit log visibility"),
    RoleInfo("user", "Base user permissions: create projects, directory lookups"),
    RoleInfo(
        "project-admin",
        "Full access to a project and its resources, including role management",
        scope="project",
    ),
    RoleInfo(
        "project-user",
        "Standard access within a project (CRUD workflows, run executions)",
        scope="project",
    ),
    RoleInfo("project-auditor", "Read-only access within a project", scope="project"),
    RoleInfo(
        "authenticated",
        "Default permissions granted to all authenticated users",
    ),
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def _build_policy_map() -> dict[str, PolicyInfo]:
    """Build name→PolicyInfo map from ``BUILTIN_POLICIES``."""
    return {p.name: p for p in BUILTIN_POLICIES}


def _build_role_map() -> dict[str, RoleInfo]:
    """Build name→RoleInfo map from ``BUILTIN_ROLES``."""
    return {r.name: r for r in BUILTIN_ROLES}


def _build_role_policy_names() -> dict[str, list[str]]:
    """Invert PolicyInfo.roles to get role_name→[policy_name, ...] mapping."""
    mapping: dict[str, list[str]] = {r.name: [] for r in BUILTIN_ROLES}
    for p in BUILTIN_POLICIES:
        for role_name in p.roles:
            if role_name in mapping:
                mapping[role_name].append(p.name)
    return mapping


# Module-level caches — built once at import time.
_POLICY_MAP: dict[str, PolicyInfo] = _build_policy_map()
_ROLE_MAP: dict[str, RoleInfo] = _build_role_map()
_ROLE_POLICY_NAMES: dict[str, list[str]] = _build_role_policy_names()


def get_builtin_policy(name: str) -> PolicyInfo | None:
    """Look up a built-in policy by canonical name, or ``None`` if not found."""
    return _POLICY_MAP.get(name)


def get_builtin_role(name: str) -> RoleInfo | None:
    """Look up a built-in role by name, or ``None`` if not found."""
    return _ROLE_MAP.get(name)


def is_builtin_role(name: str) -> bool:
    """Return ``True`` if *name* is a built-in role."""
    return name in _ROLE_MAP


def is_builtin_policy(name: str) -> bool:
    """Return ``True`` if *name* is a built-in policy."""
    return name in _POLICY_MAP


def builtin_role_policy_names(role_name: str) -> list[str]:
    """Return the policy names assigned to a built-in role."""
    return list(_ROLE_POLICY_NAMES.get(role_name, []))


def builtin_roles_with_system_grant(resource: str, action: str) -> frozenset[str]:
    """Return builtin role names that have a system-scope allow grant for resource:action.

    System scope means scope in ("any", "system", "").  Used to build fast-path
    sets at module load time — zero DB queries, zero OPA calls.
    """
    return frozenset(
        role_name
        for p in BUILTIN_POLICIES
        if p.resource == resource and p.action == action and p.scope in ("any", "system", "")
        for role_name in p.roles
    )


def builtin_policy_uuid(name: str) -> UUID:
    """Deterministic UUID for a built-in policy (stable across restarts)."""
    return uuid5(_BUILTIN_NS, f"policy:{name}")


def builtin_role_uuid(name: str) -> UUID:
    """Deterministic UUID for a built-in role (stable across restarts)."""
    return uuid5(_BUILTIN_NS, f"role:{name}")


def resolve_builtin_policy_statements(name: str) -> list[dict[str, Any]]:
    """Return Rego statement dicts for a built-in policy, or empty list."""
    p = _POLICY_MAP.get(name)
    return list(p.statements) if p else []


def resolve_builtin_role_statements(role_name: str) -> list[dict[str, Any]]:
    """Return all Rego statement dicts for a built-in role's policies."""
    policy_names = _ROLE_POLICY_NAMES.get(role_name, [])
    result: list[dict[str, Any]] = []
    for pn in policy_names:
        result.extend(resolve_builtin_policy_statements(pn))
    return result
