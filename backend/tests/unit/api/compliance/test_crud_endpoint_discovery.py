"""Tests for CRUD endpoint discovery mechanism."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.api.compliance.endpoint_discovery import (
    _get_response_schema_ref,
    _has_path_parameter,
    _resolve_response_properties,
    _resolve_success_response_properties,
    discover_create_endpoints,
    discover_delete_endpoints,
    discover_read_endpoints,
    discover_update_endpoints,
    load_all_crud_exclusions,
    load_crud_exclusions,
)


@pytest.fixture(scope="module")
def read_endpoints():
    """Discover read endpoints once for all tests."""
    return discover_read_endpoints()


@pytest.fixture(scope="module")
def create_endpoints():
    """Discover create endpoints once for all tests."""
    return discover_create_endpoints()


@pytest.fixture(scope="module")
def update_endpoints():
    """Discover update endpoints once for all tests."""
    return discover_update_endpoints()


@pytest.fixture(scope="module")
def delete_endpoints():
    """Discover delete endpoints once for all tests."""
    return discover_delete_endpoints()


@pytest.mark.unit
class TestReadDiscovery:
    """Tests for single-resource GET endpoint discovery."""

    def test_discovers_known_read_endpoints(self, read_endpoints) -> None:
        """Discovers standard get_ prefixed single-resource endpoints."""
        operation_ids = {ep.operation_id for ep in read_endpoints}

        assert "get_project" in operation_ids
        assert "get_credential" in operation_ids
        assert "get_workflow" in operation_ids

    def test_excludes_list_endpoints(self, read_endpoints) -> None:
        """Does not discover list operations."""
        operation_ids = {ep.operation_id for ep in read_endpoints}

        assert "list_projects" not in operation_ids
        assert "list_users" not in operation_ids

    def test_all_reads_are_get_method(self, read_endpoints) -> None:
        """All read endpoints use GET method."""
        for ep in read_endpoints:
            assert ep.method == "GET", f"{ep.operation_id} should be GET, got {ep.method}"

    def test_all_reads_have_path_parameter(self, read_endpoints) -> None:
        """All read endpoints have a path parameter (e.g., {id})."""
        for ep in read_endpoints:
            assert _has_path_parameter(ep.path), f"{ep.operation_id} path {ep.path} should have a parameter"


@pytest.mark.unit
class TestCreateDiscovery:
    """Tests for resource-creation POST endpoint discovery."""

    def test_discovers_standard_create_endpoints(self, create_endpoints) -> None:
        """Discovers create_ prefixed endpoints."""
        operation_ids = {ep.operation_id for ep in create_endpoints}

        assert "create_project" in operation_ids
        assert "create_workflow" in operation_ids
        assert "create_credential" in operation_ids

    def test_discovers_non_standard_creates(self, create_endpoints) -> None:
        """Discovers create endpoints without create_ prefix via structural fallback."""
        operation_ids = {ep.operation_id for ep in create_endpoints}

        assert "attach_user_identity" in operation_ids

    def test_rejects_action_endpoints_by_prefix(self) -> None:
        """Action verb prefixes are rejected by the heuristic, not by exclusions."""
        all_ids = {ep.operation_id for ep in discover_create_endpoints(apply_exclusions=False)}

        assert "disable_service_account" not in all_ids
        assert "enable_service_account" not in all_ids
        assert "publish_workflow_version" not in all_ids
        assert "restore_workflow_version" not in all_ids
        assert "unpublish_workflow" not in all_ids

    def test_all_creates_are_post_method(self, create_endpoints) -> None:
        """All create endpoints use POST method."""
        for ep in create_endpoints:
            assert ep.method == "POST", f"{ep.operation_id} should be POST, got {ep.method}"


@pytest.mark.unit
class TestUpdateDiscovery:
    """Tests for single-resource update endpoint discovery."""

    def test_discovers_patch_endpoints(self, update_endpoints) -> None:
        """Discovers PATCH update endpoints."""
        patch_ids = {ep.operation_id for ep in update_endpoints if ep.method == "PATCH"}
        assert len(patch_ids) > 0, "Should discover at least one PATCH endpoint"

    def test_discovers_put_endpoints(self, update_endpoints) -> None:
        """Discovers PUT update endpoints."""
        put_ids = {ep.operation_id for ep in update_endpoints if ep.method == "PUT"}
        assert len(put_ids) > 0, "Should discover at least one PUT endpoint"

    def test_excludes_bulk_update_endpoints(self, update_endpoints) -> None:
        """Does not discover bulk_update_ prefixed endpoints."""
        for ep in update_endpoints:
            assert not ep.operation_id.startswith("bulk_update_"), (
                f"{ep.operation_id} is a bulk update and should be excluded"
            )

    def test_all_updates_are_patch_or_put(self, update_endpoints) -> None:
        """All update endpoints use PATCH or PUT method."""
        for ep in update_endpoints:
            assert ep.method in {"PATCH", "PUT"}, f"{ep.operation_id} should be PATCH or PUT, got {ep.method}"


@pytest.mark.unit
class TestDeleteDiscovery:
    """Tests for delete endpoint discovery."""

    def test_discovers_known_delete_endpoints(self, delete_endpoints) -> None:
        """Discovers standard delete endpoints."""
        operation_ids = {ep.operation_id for ep in delete_endpoints}

        assert "delete_credential" in operation_ids
        assert "delete_group" in operation_ids

    def test_all_deletes_are_delete_method(self, delete_endpoints) -> None:
        """All delete endpoints use DELETE method."""
        for ep in delete_endpoints:
            assert ep.method == "DELETE", f"{ep.operation_id} should be DELETE, got {ep.method}"


@pytest.mark.unit
class TestHelperFunctions:
    """Tests for helper functions used in CRUD discovery."""

    def test_has_path_parameter(self) -> None:
        """Detects path parameters in URL paths."""
        assert _has_path_parameter("/projects/{project_id}")
        assert _has_path_parameter("/users/{user_id}/roles/{role_id}")
        assert not _has_path_parameter("/projects")
        assert not _has_path_parameter("/health")

    def test_get_response_schema_ref_with_status_code(self) -> None:
        """Extracts $ref from non-200 responses."""
        operation: dict[str, Any] = {
            "responses": {
                "201": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ProjectRead"}}}}
            }
        }
        assert _get_response_schema_ref(operation, "201") == "#/components/schemas/ProjectRead"
        assert _get_response_schema_ref(operation, "200") == ""

    def test_resolve_response_properties(self) -> None:
        """Resolves response schema properties via $ref lookup."""
        operation: dict[str, Any] = {
            "responses": {
                "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ProjectRead"}}}}
            }
        }
        schemas: dict[str, Any] = {
            "ProjectRead": {"properties": {"id": {"type": "string"}, "name": {"type": "string"}}}
        }
        props = _resolve_response_properties(operation, schemas, "200")
        assert "id" in props
        assert "name" in props

    def test_resolve_response_properties_no_ref(self) -> None:
        """Returns empty dict when no $ref is present."""
        operation: dict[str, Any] = {
            "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}}
        }
        assert _resolve_response_properties(operation, {}, "200") == {}

    def test_resolve_success_response_properties(self) -> None:
        """Finds the first 2xx response with properties."""
        operation: dict[str, Any] = {
            "responses": {
                "201": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Created"}}}},
                "400": {},
            }
        }
        schemas: dict[str, Any] = {"Created": {"properties": {"id": {"type": "string"}}}}
        props = _resolve_success_response_properties(operation, schemas)
        assert "id" in props

    def test_resolve_success_response_properties_empty_empty(self) -> None:
        """Returns empty dict when no 2xx responses have properties."""
        operation: dict[str, Any] = {"responses": {"400": {}, "500": {}}}
        assert _resolve_success_response_properties(operation, {}) == {}


@pytest.mark.unit
class TestExclusionLoading:
    """Tests for CRUD exclusion loading functions."""

    def test_load_crud_exclusions_returns_set(self) -> None:
        """load_crud_exclusions returns a set of operation IDs."""
        excluded = load_crud_exclusions("create")
        assert isinstance(excluded, set)
        assert "create_ws_ticket" in excluded

    def test_load_crud_exclusions_filters_by_type(self) -> None:
        """Only returns exclusions matching the requested crud_type."""
        create_excluded = load_crud_exclusions("create")
        read_excluded = load_crud_exclusions("read")

        assert "create_ws_ticket" in create_excluded
        assert "create_ws_ticket" not in read_excluded

    def test_load_crud_exclusions_unknown_type(self) -> None:
        """Returns empty set for unknown crud_type."""
        excluded = load_crud_exclusions("nonexistent")
        assert excluded == set()

    def test_load_all_crud_exclusions(self) -> None:
        """load_all_crud_exclusions returns full data dict."""
        data = load_all_crud_exclusions()
        assert isinstance(data, dict)
        assert "exclusions" in data
        assert isinstance(data["exclusions"], list)
        assert len(data["exclusions"]) > 0


@pytest.mark.unit
class TestApplyExclusionsFlag:
    """Tests for the apply_exclusions parameter across all discovery functions."""

    def test_apply_exclusions_false_returns_more_creates(self) -> None:
        """Create discovery with apply_exclusions=False includes excluded endpoints."""
        included = discover_create_endpoints(apply_exclusions=True)
        full = discover_create_endpoints(apply_exclusions=False)
        assert len(full) > len(included), "Full list should be larger than filtered list"

    def test_discovery_is_deterministic(self) -> None:
        """Discovery produces same results on multiple runs."""
        for fn in [
            discover_read_endpoints,
            discover_create_endpoints,
            discover_update_endpoints,
            discover_delete_endpoints,
        ]:
            run1 = {ep.operation_id for ep in fn()}
            run2 = {ep.operation_id for ep in fn()}
            assert run1 == run2


@pytest.mark.unit
class TestEndpointValidation:
    """Validates structural properties of discovered CRUD endpoints."""

    def test_all_endpoints_have_valid_paths(
        self, read_endpoints, create_endpoints, update_endpoints, delete_endpoints
    ) -> None:
        """All discovered endpoints have paths starting with /."""
        for ep in [*read_endpoints, *create_endpoints, *update_endpoints, *delete_endpoints]:
            assert ep.path.startswith("/"), f"{ep.operation_id} path should start with /: {ep.path}"

    def test_no_aap_endpoints_in_crud(
        self, read_endpoints, create_endpoints, update_endpoints, delete_endpoints
    ) -> None:
        """AAP proxy endpoints are excluded from all CRUD discovery."""
        for ep in [*read_endpoints, *create_endpoints, *update_endpoints, *delete_endpoints]:
            assert "Ansible Automation Platform Proxy" not in ep.tags, (
                f"{ep.operation_id} is an AAP proxy endpoint and should be excluded"
            )

    def test_no_overlap_between_read_and_list(self, read_endpoints) -> None:
        """Read endpoints should not include list operations."""
        for ep in read_endpoints:
            assert not ep.operation_id.startswith("list_"), (
                f"{ep.operation_id} looks like a list endpoint, should not be in reads"
            )
