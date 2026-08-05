"""Endpoint discovery from OpenAPI specification.

This module discovers all endpoints from the bundled OpenAPI spec and
extracts their metadata (path, operation ID, response type, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Callable

from syntara.core.router.loader import load_openapi_schema

_ACTION_OPERATION_PREFIXES = (
    "disable_",
    "enable_",
    "publish_",
    "unpublish_",
    "restore_",
    "rotate_",
    "retry_",
)

# OpenAPI tag for AAP Controller BFF proxy endpoints (locked to upstream response shape).
_AAP_PROXY_TAG = "Ansible Automation Platform Proxy"

EXCLUSIONS_FILE = Path(__file__).parent / "list_compliance_exclusions.yaml"
CRUD_EXCLUSIONS_FILE = Path(__file__).parent / "crud_compliance_exclusions.yaml"

_spec_cache: tuple[dict[str, Any], dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Shared data structures and helpers
# ---------------------------------------------------------------------------


@dataclass
class EndpointInfo:
    """Information about a discovered endpoint.

    Attributes:
        path: API path
        operation_id: OpenAPI operation ID
        method: HTTP method
        response_type: Response type name
        array_field: Name of array field in response

    """

    path: str
    operation_id: str
    method: str
    response_type: str
    array_field: str
    tags: list[str]


def _load_spec() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the OpenAPI spec and return (paths, schemas). Cached after first call."""
    global _spec_cache  # noqa: PLW0603
    if _spec_cache is not None:
        return _spec_cache
    schema = load_openapi_schema("openapi.yaml")
    if schema is None:
        msg = "Failed to load OpenAPI spec from syntara.schemas.openapi.yaml"
        raise FileNotFoundError(msg)
    spec = schema.schema_data
    _spec_cache = spec.get("paths", {}), spec.get("components", {}).get("schemas", {})
    return _spec_cache


def _reset_spec_cache() -> None:
    """Clear the cached spec so the next _load_spec() call reloads from disk."""
    global _spec_cache  # noqa: PLW0603
    _spec_cache = None


def _load_yaml_exclusions(path: Path) -> dict[str, Any]:
    """Load exclusion data from a YAML file, returning a dict with an 'exclusions' list."""
    if not path.exists():
        return {"exclusions": []}
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data.get("exclusions"), list):
        data["exclusions"] = []
    return data


def _get_response_schema_ref(operation: dict[str, Any], status_code: str = "200") -> str:
    """Extract schema $ref from an operation's response.

    Args:
        operation: OpenAPI operation object
        status_code: HTTP status code to look up (default "200")

    Returns:
        Schema reference string (e.g., "#/components/schemas/ResourcesResponse_WorkflowRead_")
        or empty string if not found

    """
    responses = operation.get("responses", {})
    success_response = responses.get(status_code, {})
    content = success_response.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    ref: str = schema.get("$ref", "")
    return ref


def _get_array_field_from_properties(properties: dict[str, Any]) -> str:
    """Extract the array field name from response schema properties.

    Returns the first array field found. For list endpoint responses, there is
    typically only one primary array field (resources, results, users, etc.).

    If multiple array fields exist, returns the first one encountered (dict iteration order).
    This is acceptable because list responses should only have one primary collection field.

    Args:
        properties: Response schema properties dictionary

    Returns:
        Array field name (e.g., "resources", "results", "users") or empty string if none

    """
    for field_name, field_schema in properties.items():
        if field_schema.get("type") == "array":
            return field_name

    return ""


def _has_path_parameter(path: str) -> bool:
    """Check if a path contains a parameter segment like {id}."""
    return "{" in path


def _resolve_response_properties(
    operation: dict[str, Any],
    schemas: dict[str, Any],
    status_code: str = "200",
) -> dict[str, Any]:
    """Resolve response schema properties for a given status code.

    Uses _get_response_schema_ref to find the $ref, then looks up properties.
    """
    ref = _get_response_schema_ref(operation, status_code)
    if not ref:
        return {}
    schema_name = ref.split("/")[-1]
    resolved = schemas.get(schema_name, {})
    return dict(resolved.get("properties", {}))


def _resolve_success_response_properties(
    operation: dict[str, Any],
    schemas: dict[str, Any],
) -> dict[str, Any]:
    """Resolve response schema properties from the first 2xx response found.

    Relies on dict iteration order (insertion order, Python 3.7+) matching the
    YAML parse order. Fine in practice — endpoints rarely declare multiple 2xx responses.
    """
    responses = operation.get("responses", {})
    for code in responses:
        if code.startswith("2"):
            props = _resolve_response_properties(operation, schemas, code)
            if props:
                return props
    return {}


def is_list_operation(operation_id: str, properties: dict[str, Any]) -> bool:
    """Check if an operation is a list endpoint.

    Uses two detection methods:
    1. Fast path: Check if operation_id starts with "list_" (convention)
    2. Fallback: Inspect response schema - must have array field but NO
       single-resource identifier (like 'id'). This distinguishes list
       responses from single resources that happen to have array fields.

    This catches both standard list operations (list_workflows) and
    query operations that return lists (who_can, what_can_i).

    Args:
        operation_id: OpenAPI operation ID
        properties: Response schema properties dictionary

    Returns:
        True if this is a list operation

    """
    # Fast path: follows naming convention
    if operation_id.startswith("list_"):
        return True

    # Fallback: has array field but NOT a single-resource response
    # Single resources have identifier fields
    has_identifier = "id" in properties
    has_array_field = bool(_get_array_field_from_properties(properties))

    return has_array_field and not has_identifier


# ---------------------------------------------------------------------------
# List endpoint discovery
# ---------------------------------------------------------------------------


def load_exclusions() -> dict[str, Any]:
    """Load list endpoint exclusions from YAML file."""
    return _load_yaml_exclusions(EXCLUSIONS_FILE)


def discover_list_endpoints() -> list[EndpointInfo]:
    """Discover all list endpoints from the OpenAPI specification.

    Parses the bundled OpenAPI spec and extracts metadata for all list endpoints.

    Returns:
        List of EndpointInfo objects for all discovered list endpoints.
        Compliance tests will validate each endpoint's behavior.

    Raises:
        FileNotFoundError: If the OpenAPI spec cannot be loaded

    Example:
        >>> endpoints = discover_list_endpoints()
        >>> print(f"Found {len(endpoints)} list endpoints")
        >>> for ep in endpoints:
        ...     print(f"{ep.operation_id}: {ep.response_type}")

    """
    paths, schemas = _load_spec()

    endpoints: list[EndpointInfo] = []

    for path, path_item in paths.items():
        # Check GET (standard) and POST (query endpoints like who_can)
        for method in ["get", "post"]:
            operation = path_item.get(method)
            if not operation:
                continue

            operation_id = operation.get("operationId", "")
            schema_ref = _get_response_schema_ref(operation)

            # Skip endpoints without JSON response schemas
            if not schema_ref:
                continue

            # Extract response type from schema reference
            response_type = schema_ref.split("/")[-1]

            # Look up response schema once
            response_schema = schemas.get(response_type, {})
            properties = response_schema.get("properties", {})

            # Check if this is a list operation
            if not is_list_operation(operation_id, properties):
                continue

            # Extract array field name
            array_field = _get_array_field_from_properties(properties)

            endpoint_info = EndpointInfo(
                path=path,
                operation_id=operation_id,
                method=method.upper(),
                response_type=response_type,
                array_field=array_field,
                tags=operation.get("tags", []),
            )

            endpoints.append(endpoint_info)

    return endpoints


def discover_testable_list_endpoints() -> list[EndpointInfo]:
    """Discover list endpoints that should be tested for compliance.

    Filters out:
    - AAP proxy endpoints (tagged "Ansible Automation Platform Proxy" in OpenAPI spec, locked to upstream format)
    - Explicitly excluded endpoints from list_compliance_exclusions.yaml

    Includes:
    - Parameterized endpoints (with path parameters like {project_id})

    Returns:
        List of EndpointInfo objects for all testable list endpoints.

    Note:
        This function combines discovery and filtering so both parametrize
        decorators and fixtures can call it directly.

    """
    all_list_endpoints = discover_list_endpoints()
    exclusions = load_exclusions()

    excluded_operation_ids = {exc["operation_id"] for exc in exclusions.get("exclusions", []) if "operation_id" in exc}

    # Filter AAP proxy endpoints and excluded endpoints
    return [
        ep
        for ep in all_list_endpoints
        if _AAP_PROXY_TAG not in ep.tags and ep.operation_id not in excluded_operation_ids
    ]


# ---------------------------------------------------------------------------
# CRUD endpoint discovery
# ---------------------------------------------------------------------------


def load_crud_exclusions(crud_type: str) -> set[str]:
    """Load excluded operation IDs for a specific CRUD type.

    Args:
        crud_type: One of "read", "create", "update", "delete"

    Returns:
        Set of excluded operation_id strings

    """
    data = _load_yaml_exclusions(CRUD_EXCLUSIONS_FILE)
    return {exc["operation_id"] for exc in data.get("exclusions", []) if exc.get("crud_type") == crud_type}


def load_all_crud_exclusions() -> dict[str, Any]:
    """Load the full CRUD exclusions data for maintenance tests."""
    return _load_yaml_exclusions(CRUD_EXCLUSIONS_FILE)


def _discover_crud_endpoints(
    crud_type: str,
    methods: list[str],
    qualifies: Callable[[str, str, dict[str, Any], dict[str, Any]], bool],
    *,
    apply_exclusions: bool = True,
) -> list[EndpointInfo]:
    """Shared skeleton for CRUD endpoint discovery.

    Handles spec loading, path iteration, AAP filtering, exclusion application,
    and EndpointInfo construction. Each public discover_*_endpoints function
    passes a qualifier callback that encapsulates its type-specific logic.

    Args:
        crud_type: One of "read", "create", "update", "delete"
        methods: HTTP methods to inspect (e.g., ["get"], ["patch", "put"])
        qualifies: Callback (operation_id, path, operation, schemas) -> bool
            that decides whether a given operation should be included
        apply_exclusions: If True, filter out excluded endpoints

    """
    paths, schemas = _load_spec()
    excluded = load_crud_exclusions(crud_type) if apply_exclusions else set()
    endpoints: list[EndpointInfo] = []

    for path, path_item in paths.items():
        for method in methods:
            operation = path_item.get(method)
            if not operation:
                continue

            operation_id = operation.get("operationId", "")
            tags = operation.get("tags", [])

            if _AAP_PROXY_TAG in tags:
                continue

            if not qualifies(operation_id, path, operation, schemas):
                continue

            if apply_exclusions and operation_id in excluded:
                continue

            endpoints.append(
                EndpointInfo(
                    path=path,
                    operation_id=operation_id,
                    method=method.upper(),
                    response_type="",
                    array_field="",
                    tags=tags,
                )
            )

    return endpoints


def discover_read_endpoints(*, apply_exclusions: bool = True) -> list[EndpointInfo]:
    """Discover single-resource GET endpoints.

    An operation qualifies only if all of the following hold:
    1. operation_id starts with "get_"
    2. path contains a parameter segment (e.g. {id})
    3. the 200 response schema has an "id" property

    This excludes list endpoints, aggregations, context endpoints (/me), and utilities.
    Unlike create discovery, there is no structural fallback for non-get_ names.

    Args:
        apply_exclusions: If True, filter out excluded endpoints. Set to False
            for exclusion maintenance tests that need the full list.

    """

    def qualifies(
        operation_id: str,
        path: str,
        operation: dict[str, Any],
        schemas: dict[str, Any],
    ) -> bool:
        if not operation_id.startswith("get_"):
            return False
        if not _has_path_parameter(path):
            return False
        return "id" in _resolve_response_properties(operation, schemas, "200")

    return _discover_crud_endpoints("read", ["get"], qualifies, apply_exclusions=apply_exclusions)


def discover_create_endpoints(*, apply_exclusions: bool = True) -> list[EndpointInfo]:
    """Discover resource-creation POST endpoints.

    Two-tier detection:
    1. Fast path: operation_id starts with "create_"
    2. Fallback: POST + response has "id" + not a list + not an action verb prefix

    The fallback catches non-standard creates (attach_user_identity,
    setup_aap_oidc_provider) without relying on YAML for action false positives.

    Args:
        apply_exclusions: If True, filter out excluded endpoints. Set to False
            for exclusion maintenance tests that need the full list.

    """

    def qualifies(
        operation_id: str,
        _path: str,
        operation: dict[str, Any],
        schemas: dict[str, Any],
    ) -> bool:
        if operation_id.startswith("create_"):
            return True
        if operation_id.startswith(_ACTION_OPERATION_PREFIXES):
            return False
        properties = _resolve_success_response_properties(operation, schemas)
        if "id" not in properties:
            return False
        return not is_list_operation(operation_id, properties)

    return _discover_crud_endpoints("create", ["post"], qualifies, apply_exclusions=apply_exclusions)


def discover_update_endpoints(*, apply_exclusions: bool = True) -> list[EndpointInfo]:
    """Discover single-resource update endpoints (PATCH and PUT).

    Detection: PATCH or PUT method, excluding bulk_update_ prefixed endpoints
    which operate on collections rather than single resources.

    Args:
        apply_exclusions: If True, filter out excluded endpoints. Set to False
            for exclusion maintenance tests that need the full list.

    """
    return _discover_crud_endpoints(
        "update",
        ["patch", "put"],
        lambda op_id, *_: not op_id.startswith("bulk_update_"),
        apply_exclusions=apply_exclusions,
    )


def discover_delete_endpoints(*, apply_exclusions: bool = True) -> list[EndpointInfo]:
    """Discover delete endpoints.

    Detection: DELETE method. Every DELETE operation in this API is a genuine
    resource deletion.

    Args:
        apply_exclusions: If True, filter out excluded endpoints. Set to False
            for exclusion maintenance tests that need the full list.

    """
    return _discover_crud_endpoints("delete", ["delete"], lambda *_: True, apply_exclusions=apply_exclusions)
