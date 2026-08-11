"""Verify all state-changing project endpoints have @audit decorators."""

import pytest
from fastapi.routing import APIRoute

from syntara.projects.router import router

MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _get_mutating_endpoints() -> list[tuple[str, str, str]]:
    """Return (method, path, function_name) for every mutating route."""
    endpoints = []
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in (route.methods or set()) & MUTATING_METHODS:
            endpoints.append((method, route.path, route.endpoint.__name__))
    return sorted(endpoints, key=lambda x: (x[1], x[0]))


@pytest.mark.parametrize(
    ("method", "path", "fn_name"),
    _get_mutating_endpoints(),
    ids=[f"{m} {p}" for m, p, _ in _get_mutating_endpoints()],
)
def test_mutating_endpoint_has_audit_decorator(method: str, path: str, fn_name: str) -> None:
    """Every POST/PATCH/PUT/DELETE endpoint must be wrapped by @audit."""
    route = next(
        r
        for r in router.routes
        if isinstance(r, APIRoute) and r.endpoint.__name__ == fn_name and method in (r.methods or set())
    )
    assert hasattr(route.endpoint, "__wrapped__"), f"{method} {path} ({fn_name}) is missing the @audit decorator"
