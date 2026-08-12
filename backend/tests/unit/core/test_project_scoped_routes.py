"""Verify that every project-associated model has project-scoped routes.

When a model has a ``project_id`` foreign key to ``projects.id``, callers
should be able to list (at minimum) that resource under
``/projects/{project_id}/...``.  This test catches the case where a developer
adds a project FK to a model but forgets to wire up project-scoped endpoints.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import SQLModel

import syntara

# ---------------------------------------------------------------------------
# Route path segments that correspond to each project-scoped model.
# Maps model class name → the path segment expected under /{project_id}/.
# If a new model with project_id is added, add a mapping here — the test
# will tell you what's missing.
# ---------------------------------------------------------------------------
_MODEL_TO_ROUTE_SEGMENT: dict[str, str] = {
    "Workflow": "/workflows",
    "Execution": "/executions",
    "ApprovalRequest": "/approvals",
    "Credential": "/credentials",
    "FileMetadata": "/files",
    "Role": "/roles",
    "Policy": "/policies",
    "RoleAssignment": "/role_assignments",
    "ServiceAccount": "/service_accounts",
    "Invocation": "/invocations",
}

# Junction/internal tables with project_id FK that are not first-class
# resources and don't need their own project-scoped endpoints.
_JUNCTION_TABLES: set[str] = {
    "IntegrationProjectAssignment",
}

# Models that have a project_id FK but no list route yet.
# Add the route, then move the model out of this set.
_MODELS_WITHOUT_LIST_ROUTE: set[str] = {
    "Execution",
    "FileMetadata",
    "Invocation",
    "ServiceAccount",
}


def _discover_project_models() -> list[tuple[str, type[SQLModel]]]:
    """Find all SQLModel table classes with a project_id FK to projects.id."""
    base = Path(syntara.__file__).parent
    for info in pkgutil.walk_packages([str(base)], prefix="syntara."):
        try:
            importlib.import_module(info.name)
        except Exception:  # noqa: S112
            continue

    results: list[tuple[str, type[SQLModel]]] = []
    seen: set[str] = set()
    for cls in SQLModel.__subclasses__():
        _collect_table_models(cls, results, seen)
    return results


def _collect_table_models(
    cls: type[Any],
    results: list[tuple[str, type[SQLModel]]],
    seen: set[str],
) -> None:
    key = f"{cls.__module__}.{cls.__qualname__}"
    if key in seen:
        return
    seen.add(key)

    if _is_project_scoped_table(cls):
        results.append((cls.__name__, cls))

    for sub in cls.__subclasses__():
        _collect_table_models(sub, results, seen)


def _is_project_scoped_table(cls: type[Any]) -> bool:
    table_config = getattr(cls, "__table__", None)
    if table_config is None:
        return False
    for col in table_config.columns:
        if col.name == "project_id":
            for fk in col.foreign_keys:
                if str(fk.target_fullname) == "projects.id":
                    return True
    return False


def _get_project_router_paths() -> set[str]:
    """Extract all route paths registered on the projects router."""
    from syntara.projects.router import router

    paths: set[str] = set()
    for route in router.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


class TestProjectScopedRouteCoverage:
    """Every model with project_id FK must have project-scoped routes."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.models = _discover_project_models()
        self.route_paths = _get_project_router_paths()

    def test_all_project_models_discovered(self) -> None:
        """Sanity: we find the models we know about."""
        names = {name for name, _ in self.models}
        assert "Workflow" in names
        assert "Credential" in names
        assert "Execution" in names
        assert "ApprovalRequest" in names

    def test_mapping_covers_all_project_models(self) -> None:
        """Every project-scoped model must have an entry in _MODEL_TO_ROUTE_SEGMENT.

        If this fails, a new model was added with project_id but the mapping
        wasn't updated — add it and create the project-scoped routes.
        """
        unmapped = []
        for name, _ in self.models:
            if name in _JUNCTION_TABLES:
                continue
            if name not in _MODEL_TO_ROUTE_SEGMENT:
                unmapped.append(name)
        assert not unmapped, (
            f"Models with project_id FK but no route mapping: {unmapped}. "
            "Add entries to _MODEL_TO_ROUTE_SEGMENT in this test and create "
            "project-scoped routes in projects/router.py."
        )

    def test_each_project_model_has_list_route(self) -> None:
        """Every mapped model must have at least a GET list route under /projects/{project_id}/."""
        missing = []
        for name, _ in self.models:
            if name in _MODELS_WITHOUT_LIST_ROUTE:
                continue
            segment = _MODEL_TO_ROUTE_SEGMENT.get(name)
            if segment is None:
                continue
            expected = f"/projects/{{project_id}}{segment}"
            has_list = any(p == expected for p in self.route_paths)
            if not has_list:
                missing.append((name, expected))
        assert not missing, (
            f"Models missing project-scoped list route: "
            f"{[(n, p) for n, p in missing]}. "
            "Add a GET endpoint in projects/router.py."
        )

    def test_project_routes_have_permission_checker(self) -> None:
        """Every project-scoped route must have a permission dependency."""
        from syntara.authz.dependencies import PermissionChecker
        from syntara.projects.router import router

        authz_dep_types = (PermissionChecker,)
        authz_dep_names = {"_NoPermissionSentinel", "VisibilityFilter"}

        from fastapi.routing import APIRoute

        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            if "{project_id}" not in route.path:
                continue
            deps = route.dependant.dependencies
            has_perm = any(
                isinstance(d.call, authz_dep_types) or type(d.call).__name__ in authz_dep_names for d in deps
            )
            assert has_perm, (
                f"Route {route.methods} {route.path} has no PermissionChecker or NO_PERMISSION dependency. "
                "All project-scoped endpoints must have authorization."
            )
