"""AUTH-1: Route coverage — all non-health routes require authentication.

Structural guard that enumerates every registered FastAPI route and verifies
``get_current_user`` appears in its dependency chain. Adding a route without
authentication causes this test to fail.

Routes exempted by design:
- Health / docs / internal endpoints (already excluded from middleware)
- Auth routes (/auth/*) — use dedicated token deps or are public
- Webhook routes (/webhooks/*) — use service account Bearer token authentication (get_webhook_caller)
- Public utility routes (resource_actions, validate_name)
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import FastAPI

from syntara.api.constants import API_V1_PATH_PREFIX, EXCLUDED_PATH_PREFIXES, EXCLUDED_PATHS
from syntara.auth.dependencies import get_current_user
from syntara.core.router_discovery import discover_and_register_routers, iter_api_routes

pytestmark = [pytest.mark.integration]

AUTH_EXEMPT_PREFIXES = (
    f"{API_V1_PATH_PREFIX}/auth/",
    f"{API_V1_PATH_PREFIX}/webhooks/",
)

AUTH_EXEMPT_PATHS = frozenset(
    {
        f"{API_V1_PATH_PREFIX}/authz/resource_actions",
        f"{API_V1_PATH_PREFIX}/authz/validate_name",
    }
)


def _is_excluded(path: str) -> bool:
    if path in EXCLUDED_PATHS or path in AUTH_EXEMPT_PATHS:
        return True
    return any(path.startswith(p) for p in (*EXCLUDED_PATH_PREFIXES, *AUTH_EXEMPT_PREFIXES))


def _has_get_current_user(dependant: object, depth: int = 0) -> bool:
    """Walk the FastAPI dependency tree looking for ``get_current_user``."""
    if depth > 10 or dependant is None:
        return False
    for dep in getattr(dependant, "dependencies", []):
        call = getattr(dep, "call", None)
        if call is get_current_user:
            return True
        sub = getattr(dep, "dependency", None) or getattr(dep, "dependant", None)
        if sub is not None and _has_get_current_user(sub, depth + 1):
            return True
        if call is not None and callable(call):
            try:
                sig = inspect.signature(call.__call__ if isinstance(call, type) else call)
                if "current_user" in sig.parameters:
                    return True
            except (ValueError, TypeError):
                pass
    return False


def _route_has_auth(route: object) -> bool:
    endpoint = getattr(route, "endpoint", None)
    sig = inspect.signature(endpoint) if endpoint else None
    params = list(sig.parameters.keys()) if sig else []
    if "current_user" in params:
        return True
    return _has_get_current_user(getattr(route, "dependant", None))


@pytest.fixture(scope="module")
def discovered_app() -> FastAPI:
    """Build a FastAPI app with all routers discovered and registered."""
    app = FastAPI()
    discover_and_register_routers(app=app, prefix=API_V1_PATH_PREFIX, enable_validation=False)
    return app


class TestAUTH1RouteAuthCoverage:
    """AUTH-1: Every non-exempt API route requires authentication."""

    def test_all_non_exempt_routes_require_auth(self, discovered_app: FastAPI) -> None:
        """Fail if any non-exempt route lacks get_current_user in its dep chain."""
        unprotected: list[str] = []
        for route in iter_api_routes(discovered_app):
            path = route.path
            if _is_excluded(path):
                continue
            if not _route_has_auth(route):
                methods = ",".join(sorted(route.methods or set()))
                unprotected.append(f"{methods} {path} -> {route.endpoint.__name__}()")

        assert not unprotected, "Routes without get_current_user in dependency chain:\n" + "\n".join(
            f"  {r}" for r in unprotected
        )

    def test_at_least_one_route_discovered(self, discovered_app: FastAPI) -> None:
        """Sanity check: router discovery found routes."""
        routes = list(iter_api_routes(discovered_app))
        assert len(routes) > 50, f"Expected 50+ routes, got {len(routes)}"

    def test_exempt_routes_exist(self, discovered_app: FastAPI) -> None:
        """Sanity check: the exempted auth/webhook routes are actually present."""
        paths = {route.path for route in iter_api_routes(discovered_app)}
        assert f"{API_V1_PATH_PREFIX}/auth/login" in paths
        assert any(p.startswith(f"{API_V1_PATH_PREFIX}/webhooks/") for p in paths)
