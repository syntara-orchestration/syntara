"""Shared fixtures and utilities for compliance tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from _pytest.outcomes import Failed, Skipped

from syntara.core.router.loader import load_openapi_schema

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.unit.api.compliance.endpoint_discovery import EndpointInfo

MIN_EXCLUSION_REASON_LENGTH = 20


@pytest.fixture(scope="module")
def openapi_spec() -> dict[str, Any]:
    """Load OpenAPI spec once for all tests in a module."""
    schema = load_openapi_schema("openapi.yaml")
    if schema is None:
        pytest.fail("Failed to load OpenAPI spec")
    return schema.schema_data


def get_operation(endpoint: EndpointInfo, openapi_spec: dict[str, Any]) -> dict[str, Any]:
    """Get the OpenAPI operation object for the given endpoint."""
    paths = openapi_spec.get("paths", {})
    path_item = paths.get(endpoint.path, {})
    result: dict[str, Any] = path_item.get(endpoint.method.lower(), {})
    return result


def get_response_codes(endpoint: EndpointInfo, openapi_spec: dict[str, Any]) -> set[str]:
    """Get all declared response status codes for an endpoint."""
    operation = get_operation(endpoint, openapi_spec)
    return set(operation.get("responses", {}).keys())


def check_passes(
    check_fn: Callable[..., object],
    endpoint: EndpointInfo,
    openapi_spec: dict[str, Any],
) -> bool:
    """Run a compliance check and return True if it passes or is skipped, False if it fails."""
    try:
        check_fn(endpoint, openapi_spec)
    except (AssertionError, Failed):
        return False
    except Skipped:
        # Skipped → passing: some checks legitimately skip (e.g. create endpoints
        # skip the 404 check). A skip is not a failure for staleness purposes.
        return True
    return True
