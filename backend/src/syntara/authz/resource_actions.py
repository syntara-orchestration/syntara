"""Dynamic registry of resource types and their valid actions.

Instead of maintaining a static dictionary, this module builds the
resource-actions catalog at startup by introspecting the FastAPI route
dependencies (``PermissionChecker``, ``ProjectScopeFilter``) and merging
with ``BUILTIN_POLICIES``.  The result is stored in a module-level holder
and on ``app.state.resource_actions`` so both request-scoped code and the
policy service can access it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.stdlib.get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level registry holder
# ---------------------------------------------------------------------------

_registry: dict[str, list[str]] | None = None
_all_pairs: frozenset[str] = frozenset()
_project_eligible: frozenset[str] = frozenset()


def _set_registry(
    resource_actions: dict[str, list[str]],
    project_eligible: frozenset[str] | None = None,
) -> None:
    """Install the dynamic registry (called once at startup)."""
    global _registry, _all_pairs, _project_eligible  # noqa: PLW0603
    _registry = resource_actions
    _all_pairs = frozenset(f"{rt}:{action}" for rt, actions in resource_actions.items() for action in actions)
    if project_eligible is not None:
        _project_eligible = project_eligible


def get_resource_actions() -> dict[str, list[str]]:
    """Return the resource-actions catalog.

    Raises:
        RuntimeError: If called before ``build_resource_actions`` has run.

    """
    if _registry is None:
        msg = "Resource-actions registry not initialized. Call build_resource_actions(app) during startup."
        raise RuntimeError(msg)
    return _registry


def get_all_resource_action_pairs() -> frozenset[str]:
    """Return every valid ``resource_type:action`` pair as a flat set."""
    if _registry is None:
        msg = "Resource-actions registry not initialized. Call build_resource_actions(app) during startup."
        raise RuntimeError(msg)
    return _all_pairs


def validate_statements(statements: list[dict[str, Any]]) -> list[str]:
    """Validate that all action strings in policy statements reference registered pairs.

    Wildcards (``resource_type:*``) are allowed if the resource type is registered.

    Returns a list of invalid action strings (empty if all valid).
    """
    registry = get_resource_actions()
    pairs = _all_pairs
    invalid: list[str] = []
    for stmt in statements:
        for action_str in stmt.get("actions", []):
            if ":" not in action_str:
                invalid.append(action_str)
                continue
            resource_type, action = action_str.split(":", 1)
            if action == "*":
                if resource_type not in registry:
                    invalid.append(action_str)
            elif action_str not in pairs:
                invalid.append(action_str)
    return invalid


def get_project_eligible_resource_types() -> frozenset[str]:
    """Return resource types that are valid at project scope.

    Derived at startup from route introspection: a resource type is
    project-eligible when its ``PermissionChecker`` references a model
    with a ``project_id`` field, or uses ``project_param`` /
    ``body_project_field``.

    Raises:
        RuntimeError: If called before ``build_resource_actions`` has run.

    """
    if _registry is None:
        msg = "Resource-actions registry not initialized. Call build_resource_actions(app) during startup."
        raise RuntimeError(msg)
    return _project_eligible


def validate_project_statements(statements: list[dict[str, Any]]) -> str | None:
    """Validate that statements are appropriate for project-scoped policies.

    Enforces two invariants:
    1. Scope must be ``"project"`` (future: attribute-based selectors
       within project scope).
    2. Actions must reference project-eligible resource types only.

    Returns a descriptive error string, or ``None`` if valid.
    """
    eligible = get_project_eligible_resource_types()

    for stmt in statements:
        scope = stmt.get("scope", "any")
        if scope != "project":
            return f"Project policies only accept scope='project', got scope='{scope}'"

        for action_str in stmt.get("actions", []):
            if ":" not in action_str:
                continue
            resource_type = action_str.split(":", 1)[0]
            if resource_type not in eligible:
                return (
                    f"Resource type '{resource_type}' is not valid at project scope. "
                    f"Allowed: {', '.join(sorted(eligible))}"
                )

    return None


# ---------------------------------------------------------------------------
# Scanner — builds the registry from live FastAPI routes + BUILTIN_POLICIES
# ---------------------------------------------------------------------------


def _get_dep_instance(dep: object) -> object | None:
    """Extract the underlying dependency instance from a Depends or Dependant."""
    inner: object | None = getattr(dep, "dependency", None)
    if inner is not None:
        return inner
    result: object | None = getattr(dep, "call", None)
    return result


def _iter_route_deps(route: object) -> list[object]:
    """Collect dependency objects from a route (route-level + param-level)."""
    deps: list[object] = []
    deps.extend(getattr(route, "dependencies", []) or [])
    dependant = getattr(route, "dependant", None)
    if dependant:
        deps.extend(getattr(dependant, "dependencies", []) or [])
    return deps


def build_resource_actions(app: FastAPI) -> dict[str, list[str]]:
    """Build the resource-actions catalog by introspecting the app.

    Sources:
    1. ``PermissionChecker`` / ``ProjectScopeFilter`` instances attached to
       registered ``APIRoute`` dependencies.
    2. ``BUILTIN_POLICIES`` entries (captures pairs like ``role-assignment:read``
       that are enforced via inline ``authorize()`` calls rather than route deps).

    The result is sorted (resource types alphabetically, actions within each
    resource type alphabetically) to produce a deterministic, API-friendly
    output.

    After building, the registry is installed in the module-level holder
    (via ``_set_registry``) and returned so the caller can also store it
    on ``app.state``.
    """
    from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter  # noqa: PLC0415
    from syntara.authz.role_conventions import BUILTIN_POLICIES  # noqa: PLC0415
    from syntara.core.router_discovery import iter_api_routes  # noqa: PLC0415

    pairs: set[tuple[str, str]] = set()
    project_eligible: set[str] = {"project"}

    for route in iter_api_routes(app):
        for dep in _iter_route_deps(route):
            inner = _get_dep_instance(dep)
            if isinstance(inner, (PermissionChecker, ProjectScopeFilter, VisibilityFilter)):
                pairs.add((inner.resource_type, inner.action))
            if isinstance(inner, PermissionChecker) and (
                inner.project_param
                or inner.body_project_field
                or (inner.resource_model and hasattr(inner.resource_model, "project_id"))
            ):
                project_eligible.add(inner.resource_type)

    for policy in BUILTIN_POLICIES:
        pairs.add((policy.resource, policy.action))

    grouped: dict[str, set[str]] = defaultdict(set)
    for resource_type, action in pairs:
        grouped[resource_type].add(action)

    result = {rt: sorted(actions) for rt, actions in sorted(grouped.items())}

    _set_registry(result, frozenset(project_eligible))
    logger.info(
        "Resource-actions registry built",
        resource_types=len(result),
        total_pairs=sum(len(a) for a in result.values()),
        project_eligible=sorted(project_eligible),
    )
    return result
