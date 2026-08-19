"""FilterableModel compliance tests.

Validates bidirectional consistency between list routes and their models:
1. Every FilterableModel dependency references a valid model with __filterable_fields__
2. Every list route that uses parse_filters should have a FilterableModel dependency
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from syntara.api.constants import API_V1_PATH_PREFIX
from syntara.core.router_discovery import discover_and_register_routers, iter_api_routes
from tools.export_openapi import _extract_filterable_model

_INFRA_PATH_PREFIXES = (
    "/health",
    "/metrics",
    "/_internal/",
)

_EXCLUSIONS_PATH = Path(__file__).parent / "list_compliance_exclusions.yaml"


def _load_excluded_operation_ids() -> set[str]:
    """Load operation IDs excluded from compliance checks."""
    data = yaml.safe_load(_EXCLUSIONS_PATH.read_text(encoding="utf-8"))
    return {e["operation_id"] for e in (data.get("exclusions") or [])}


def _is_list_route(route: object) -> bool:
    """Check if a route is a GET list endpoint (operation_id starts with 'list_' or 'get_')."""
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

    def test_list_routes_without_filterable_model(self, app):
        """List routes not in the exclusion list should have a FilterableModel dependency."""
        excluded = _load_excluded_operation_ids()
        missing = []
        for route in iter_api_routes(app):
            if not _is_list_route(route):
                continue
            op_id = getattr(route, "operation_unique_id", "") or getattr(route, "name", "") or ""
            if op_id in excluded:
                continue
            fm = _extract_filterable_model(route)
            if fm is None:
                missing.append(f"{route.path} ({op_id})")

        assert not missing, (
            "List routes missing FilterableModel dependency "
            "(add the dependency or exclude in list_compliance_exclusions.yaml):\n"
            + "\n".join(f"  - {m}" for m in missing)
        )
