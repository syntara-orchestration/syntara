"""Auth/RBAC compliance tests (AAP-77366).

Discovers all registered API endpoints and validates each has RBAC
enforcement via PermissionChecker, VisibilityFilter, or
ProjectScopeFilter.  Routes without RBAC must appear in
``auth_exclusions.yml`` under ``authenticated`` or ``public``.

How to fix a failure
--------------------
* **Missing RBAC** - add ``PermissionChecker`` or ``VisibilityFilter``
  to the route dependencies or handler params.
* **Legitimate exception** - add the route to ``auth_exclusions.yml``
  under the appropriate section with a justification.
* **Stale exclusion** - remove the entry when the route gains RBAC
  or is deleted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI

from syntara.api.constants import API_V1_PATH_PREFIX
from syntara.auth.dependencies import get_current_user, get_token_payload
from syntara.authz.dependencies import PermissionChecker, ProjectScopeFilter, VisibilityFilter
from syntara.authz.resource_actions import _get_dep_instance, _iter_route_deps
from syntara.core.router_discovery import discover_and_register_routers, iter_api_routes

# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

_RBAC_TYPES = (PermissionChecker, ProjectScopeFilter, VisibilityFilter)
_AUTHN_CALLABLES = (get_current_user, get_token_payload)


def _has_rbac(route: object) -> bool:
    """Return True if the route has an RBAC dependency."""
    for dep in _iter_route_deps(route):
        inner = _get_dep_instance(dep)
        if isinstance(inner, _RBAC_TYPES):
            return True
    return False


def _has_authn(route: object) -> bool:
    """Return True if get_current_user/get_token_payload appears anywhere in the dep tree."""
    visited: set[int] = set()

    def _walk(dependant: object) -> bool:
        dep_id = id(dependant)
        if dep_id in visited:
            return False
        visited.add(dep_id)

        if getattr(dependant, "call", None) in _AUTHN_CALLABLES:
            return True
        return any(_walk(sub) for sub in getattr(dependant, "dependencies", []) or [])

    dependant = getattr(route, "dependant", None)
    return _walk(dependant) if dependant else False


# ---------------------------------------------------------------------------
# Infrastructure paths (excluded from all compliance checks)
# ---------------------------------------------------------------------------

_INFRA_PATH_PREFIXES = (
    "/healthz/",
    "/metrics",
    "/_internal/",
    "/api_docs/",
    "/docs",
)


def _is_infra(path: str) -> bool:
    if path == "/":
        return True
    return any(path.startswith(prefix) for prefix in _INFRA_PATH_PREFIXES)


# ---------------------------------------------------------------------------
# YAML exclusion loading
# ---------------------------------------------------------------------------

_EXCLUSIONS_FILE = Path(__file__).parent / "auth_exclusions.yml"


def _load_exclusions() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Load exclusions from YAML, returning (authenticated, public) sets of (method, path)."""
    with _EXCLUSIONS_FILE.open() as f:
        data = yaml.safe_load(f) or {}

    authenticated: set[tuple[str, str]] = set()
    public: set[tuple[str, str]] = set()

    for entry in data.get("authenticated", []):
        _validate_entry(entry, "authenticated")
        authenticated.add((entry["method"], entry["path"]))

    for entry in data.get("public", []):
        _validate_entry(entry, "public")
        public.add((entry["method"], entry["path"]))

    return authenticated, public


def _validate_entry(entry: dict[str, str], section: str) -> None:
    for field in ("method", "path", "justification"):
        if field not in entry:
            msg = f"{section} exclusion missing '{field}': {entry}"
            raise ValueError(msg)
    if not entry["justification"].strip():
        msg = f"{section} exclusion for {entry['method']} {entry['path']} has empty justification"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compliance_app() -> FastAPI:
    """Build a FastAPI app with routers for route introspection only."""
    test_app = FastAPI()
    discover_and_register_routers(
        test_app,
        prefix=API_V1_PATH_PREFIX,
        enable_validation=False,
    )
    return test_app


@pytest.fixture(scope="module")
def exclusions() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Load authenticated and public exclusion sets."""
    return _load_exclusions()


# ---------------------------------------------------------------------------
# Route collection
# ---------------------------------------------------------------------------


def _collect_api_routes(app: FastAPI) -> list[tuple[str, str, object]]:
    """Return ``(method, path, route)`` for all API routes."""
    results: list[tuple[str, str, object]] = []
    for route in iter_api_routes(app):
        if _is_infra(route.path):
            continue
        for method in sorted(route.methods or []):
            results.append((method, route.path, route))
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.compliance
def test_all_endpoints_have_rbac(
    compliance_app: FastAPI,
    exclusions: tuple[set[tuple[str, str]], set[tuple[str, str]]],
) -> None:
    """Every API route must have RBAC or be in auth_exclusions.yml."""
    authenticated_exc, public_exc = exclusions
    all_exc = authenticated_exc | public_exc
    routes = _collect_api_routes(compliance_app)
    assert routes, "No API routes discovered"

    violations: list[str] = []

    for method, path, route in routes:
        if _has_rbac(route):
            continue
        if (method, path) not in all_exc:
            violations.append(
                f"  {method} {path}: no RBAC — add PermissionChecker/VisibilityFilter or add to auth_exclusions.yml"
            )

    if violations:
        pytest.fail(
            f"RBAC compliance violations ({len(violations)}):\n"
            + "\n".join(violations)
            + "\n\nFix: see auth_exclusions.yml"
        )


@pytest.mark.unit
@pytest.mark.compliance
def test_authenticated_exclusions_actually_require_authn(
    compliance_app: FastAPI,
    exclusions: tuple[set[tuple[str, str]], set[tuple[str, str]]],
) -> None:
    """Routes in the 'authenticated' section must actually require a JWT."""
    authenticated_exc, _ = exclusions
    routes = _collect_api_routes(compliance_app)
    mismatches: list[str] = []

    for method, path, route in routes:
        if _has_rbac(route):
            continue
        if (method, path) in authenticated_exc and not _has_authn(route):
            mismatches.append(f"  {method} {path}: listed as authenticated but no JWT dep found")

    if mismatches:
        pytest.fail(
            f"Auth mismatches ({len(mismatches)}):\n"
            + "\n".join(mismatches)
            + "\n\nMove to 'public' section or add get_current_user."
        )


@pytest.mark.unit
@pytest.mark.compliance
def test_public_exclusions_are_actually_public(
    compliance_app: FastAPI,
    exclusions: tuple[set[tuple[str, str]], set[tuple[str, str]]],
) -> None:
    """Routes in the 'public' section must NOT require a JWT."""
    _, public_exc = exclusions
    routes = _collect_api_routes(compliance_app)
    mismatches: list[str] = []

    for method, path, route in routes:
        if _has_rbac(route):
            continue
        if (method, path) in public_exc and _has_authn(route):
            mismatches.append(f"  {method} {path}: listed as public but requires JWT")

    if mismatches:
        pytest.fail(
            f"Auth mismatches ({len(mismatches)}):\n"
            + "\n".join(mismatches)
            + "\n\nMove to 'authenticated' section or remove get_current_user."
        )


@pytest.mark.unit
@pytest.mark.compliance
def test_no_stale_exclusions(
    compliance_app: FastAPI,
    exclusions: tuple[set[tuple[str, str]], set[tuple[str, str]]],
) -> None:
    """Exclusion entries must not reference deleted routes or routes that gained RBAC."""
    authenticated_exc, public_exc = exclusions
    routes = _collect_api_routes(compliance_app)
    route_keys = {(m, p) for m, p, _ in routes}

    stale: list[str] = []

    for section_name, section_keys in [("authenticated", authenticated_exc), ("public", public_exc)]:
        for key in section_keys:
            method, path = key
            if key not in route_keys:
                stale.append(f"  {method} {path}: route no longer exists ({section_name})")
                continue
            matching = next((r for m, p, r in routes if (m, p) == key), None)
            if matching and _has_rbac(matching):
                stale.append(f"  {method} {path}: now has RBAC — remove from {section_name}")

    if stale:
        pytest.fail(f"Stale exclusions ({len(stale)}):\n" + "\n".join(stale))
