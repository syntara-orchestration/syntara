"""Tests for list endpoint discovery mechanism."""

from __future__ import annotations

import pytest

from tests.unit.api.compliance.endpoint_discovery import (
    EndpointInfo,
    _get_array_field_from_properties,
    _get_response_schema_ref,
    discover_list_endpoints,
    discover_testable_list_endpoints,
    is_list_operation,
    load_exclusions,
)


@pytest.fixture(scope="module")
def all_endpoints():
    """Discover endpoints once for all tests."""
    return discover_list_endpoints()


@pytest.fixture(scope="module")
def testable_endpoints():
    """Discover testable endpoints once for all tests."""
    return discover_testable_list_endpoints()


@pytest.fixture(scope="module")
def exclusions():
    """Load exclusions once for all tests."""
    return load_exclusions()


@pytest.mark.unit
class TestDiscoveryBehavior:
    """Tests for endpoint discovery behavior."""

    def test_discovers_standard_list_endpoints(self, all_endpoints) -> None:
        """Discovers endpoints with list_ operationId."""
        operation_ids = {ep.operation_id for ep in all_endpoints}

        # Should find standard list operations
        assert "list_projects" in operation_ids
        assert "list_users" in operation_ids
        assert "list_credentials" in operation_ids

    def test_discovers_who_can(self, all_endpoints) -> None:
        """Discovers who_can endpoint (AAP-77347)."""
        operation_ids = {ep.operation_id for ep in all_endpoints}

        # Should discover who_can (returns array of resources)
        assert "who_can" in operation_ids

    def test_discovers_legacy_aap_endpoints(self, all_endpoints) -> None:
        """Discovers endpoints with 'results' field (legacy AAP pattern)."""
        endpoints = all_endpoints

        # Should find legacy AAP endpoints that use 'results' instead of 'resources'
        aap_endpoints = [ep for ep in endpoints if "aap_" in ep.operation_id.lower()]

        # At least some AAP endpoints should be discovered
        assert len(aap_endpoints) > 0, "Should discover at least some AAP proxy endpoints"

        # Verify they use 'results' array field (legacy pattern)
        for ep in aap_endpoints:
            assert ep.array_field == "results", f"{ep.operation_id} should use 'results' field"

    def test_excludes_single_resource_gets(self, all_endpoints) -> None:
        """Does not discover single resource GET operations."""
        operation_ids = {ep.operation_id for ep in all_endpoints}

        # Should NOT discover single resource operations (they have 'id' field)
        assert "get_project" not in operation_ids
        assert "get_user" not in operation_ids
        assert "get_credential" not in operation_ids

    def test_discovery_is_deterministic(self) -> None:
        """Discovery produces same results on multiple runs."""
        endpoints1 = discover_list_endpoints()
        endpoints2 = discover_list_endpoints()

        ids1 = {ep.operation_id for ep in endpoints1}
        ids2 = {ep.operation_id for ep in endpoints2}

        assert ids1 == ids2


@pytest.mark.unit
class TestHelperFunctions:
    """Tests for helper functions used in discovery."""

    def test_is_list_operation_with_list_prefix(self) -> None:
        """Test that list_ prefixed operations are always identified as list endpoints."""
        # Fast path: follows naming convention
        properties = {"id": "string", "name": "string"}  # Even with id field
        assert is_list_operation("list_projects", properties)
        assert is_list_operation("list_users", properties)

    def test_is_list_operation_with_array_no_id(self) -> None:
        """Test that operations with array field but no id are list endpoints."""
        properties = {"resources": {"type": "array"}, "next": {"type": "string"}}
        assert is_list_operation("who_can", properties)
        assert is_list_operation("what_can_i", properties)

    def test_is_list_operation_rejects_single_resource(self) -> None:
        """Test that operations with id field but no array are NOT list endpoints."""
        # Single resource: has id field
        properties = {"id": {"type": "string"}, "name": {"type": "string"}}
        assert not is_list_operation("get_project", properties)

        # Single resource with array field (like user.groups) - has id
        properties_with_array = {
            "id": {"type": "string"},
            "groups": {"type": "array"},
        }
        assert not is_list_operation("get_current_user", properties_with_array)

    def test_get_array_field_from_properties(self) -> None:
        """Test extracting array field name from response properties."""
        # Standard pattern: resources
        properties = {
            "resources": {"type": "array"},
            "next": {"type": "string"},
            "prev": {"type": "string"},
        }
        assert _get_array_field_from_properties(properties) == "resources"

        # Legacy AAP pattern: results
        properties_legacy = {
            "results": {"type": "array"},
            "count": {"type": "integer"},
        }
        assert _get_array_field_from_properties(properties_legacy) == "results"

        # No array field
        properties_no_array = {
            "id": {"type": "string"},
            "name": {"type": "string"},
        }
        assert _get_array_field_from_properties(properties_no_array) == ""

    def test_get_response_schema_ref(self) -> None:
        """Test extracting schema $ref from operation response."""
        operation = {
            "responses": {
                "200": {
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ProjectListResponse"}}}
                }
            }
        }
        ref = _get_response_schema_ref(operation)
        assert ref == "#/components/schemas/ProjectListResponse"

        # No ref
        operation_no_ref = {"responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}}}
        ref = _get_response_schema_ref(operation_no_ref)
        assert ref == ""


@pytest.mark.unit
class TestFiltering:
    """Tests for filtering logic (AAP endpoints and exclusions)."""

    def test_load_exclusions(self, exclusions) -> None:
        """Test loading exclusions from YAML file."""
        # Should return dict with exclusions list
        assert isinstance(exclusions, dict)
        assert "exclusions" in exclusions
        assert isinstance(exclusions["exclusions"], list)

    def test_discover_testable_list_endpoints_filters_aap(self, all_endpoints, testable_endpoints) -> None:
        """Test that AAP proxy endpoints are filtered from testable endpoints."""
        all_ids = {ep.operation_id for ep in all_endpoints}
        testable_ids = {ep.operation_id for ep in testable_endpoints}

        # AAP endpoints should be in all but not testable (tagged in OpenAPI spec)
        aap_endpoints = [ep for ep in all_endpoints if "Ansible Automation Platform Proxy" in ep.tags]
        assert len(aap_endpoints) > 0, "Should have some AAP endpoints"

        for ep in aap_endpoints:
            assert ep.operation_id in all_ids, f"{ep.operation_id} should be discovered"
            assert ep.operation_id not in testable_ids, f"{ep.operation_id} should be filtered out"

    def test_discover_testable_list_endpoints_respects_exclusions(
        self, all_endpoints, testable_endpoints, exclusions
    ) -> None:
        """Test that excluded endpoints are filtered from testable endpoints."""
        all_ids = {ep.operation_id for ep in all_endpoints}
        testable_ids = {ep.operation_id for ep in testable_endpoints}

        # Check each excluded endpoint
        for exc in exclusions.get("exclusions", []):
            op_id = exc["operation_id"]
            # May or may not be discovered (depends if it matches list criteria)
            if op_id in all_ids:
                # If discovered, should NOT be testable
                assert op_id not in testable_ids, f"{op_id} is excluded but still testable"


@pytest.mark.unit
class TestValidation:
    """Tests for validating discovered endpoint data."""

    def test_endpoint_info_dataclass(self) -> None:
        """Test EndpointInfo dataclass structure."""
        endpoint = EndpointInfo(
            path="/projects",
            operation_id="list_projects",
            method="GET",
            response_type="ProjectListResponse",
            array_field="resources",
            tags=["projects"],
        )

        assert endpoint.path == "/projects"
        assert endpoint.operation_id == "list_projects"
        assert endpoint.method == "GET"
        assert endpoint.response_type == "ProjectListResponse"
        assert endpoint.array_field == "resources"

    def test_all_discovered_endpoints_have_array_field(self, all_endpoints) -> None:
        """All discovered endpoints should have an array field name."""
        for ep in all_endpoints:
            assert ep.array_field, f"{ep.operation_id} has no array_field"
            assert isinstance(ep.array_field, str), f"{ep.operation_id} array_field is not string"

    def test_all_discovered_endpoints_have_response_type(self, all_endpoints) -> None:
        """All discovered endpoints should have a response type."""
        for ep in all_endpoints:
            assert ep.response_type, f"{ep.operation_id} has no response_type"
            assert isinstance(ep.response_type, str), f"{ep.operation_id} response_type is not string"

    def test_discovered_endpoints_have_valid_paths(self, all_endpoints) -> None:
        """All discovered endpoints should have paths from the OpenAPI spec."""
        for ep in all_endpoints:
            # Paths should start with / and not be empty
            assert ep.path.startswith("/"), f"{ep.operation_id} path should start with /: {ep.path}"
            assert len(ep.path) > 1, f"{ep.operation_id} path should not be just '/': {ep.path}"
