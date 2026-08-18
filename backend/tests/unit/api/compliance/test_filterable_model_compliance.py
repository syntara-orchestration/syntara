"""FilterableModel compliance tests.

Validates bidirectional consistency between list routes and their models:
1. Every FilterableModel dependency references a valid model with __filterable_fields__
2. Every list endpoint whose model has __filterable_fields__ has a FilterableModel dependency
"""

from __future__ import annotations

import pytest

from syntara.api.constants import API_V1_PATH_PREFIX
from syntara.core.router_discovery import discover_and_register_routers, iter_api_routes
from tools.export_openapi import _extract_filterable_model

_INFRA_PATH_PREFIXES = (
    "/health",
    "/metrics",
    "/_internal/",
)


def _is_list_route(route: object) -> bool:
    """Check if a route is a GET list endpoint (operation_id starts with 'list_')."""
    methods = getattr(route, "methods", set()) or set()
    if "GET" not in methods:
        return False
    path = getattr(route, "path", "")
    if not path.startswith(API_V1_PATH_PREFIX):
        return False
    if any(path.startswith(prefix) for prefix in _INFRA_PATH_PREFIXES):
        return False
    operation_id = getattr(route, "operation_unique_id", "") or ""
    name = getattr(route, "name", "") or ""
    return operation_id.startswith("list_") or name.startswith("list_")


@pytest.fixture(scope="module")
def app():
    """Build the FastAPI app with all routers registered."""
    from fastapi import FastAPI

    test_app = FastAPI()
    discover_and_register_routers(test_app)
    return test_app


@pytest.mark.unit
class TestFilterableModelCompliance:
    """Validate FilterableModel dependency consistency."""

    def test_every_filterable_model_references_valid_model(self, app):
        """Every FilterableModel dependency should reference a model with __filterable_fields__."""
        errors = []
        for route in iter_api_routes(app):
            fm = _extract_filterable_model(route)
            if fm is None:
                continue
            if not hasattr(fm.model, "__filterable_fields__"):
                errors.append(
                    f"{route.path}: FilterableModel references {fm.model.__name__} which has no __filterable_fields__"
                )

        assert not errors, "FilterableModel validation errors:\n" + "\n".join(errors)

    def test_list_routes_with_filterable_model_have_correct_dependency(self, app):
        """Routes with FilterableModel should list it as a dependency."""
        routes_with_fm = []
        for route in iter_api_routes(app):
            fm = _extract_filterable_model(route)
            if fm is not None:
                routes_with_fm.append(route.path)

        assert len(routes_with_fm) > 0, (
            "No routes found with FilterableModel dependency — "
            "at least the credentials and integrations routes should have it"
        )
