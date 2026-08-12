"""List endpoint compliance tests.

Validates that all list endpoints conform to pagination/filtering/sorting standards
by checking the OpenAPI specification structure.

IMPORTANT: These tests validate API CAPABILITY declarations in the OpenAPI spec,
not runtime behavior. They check:
- "Does the spec declare pagination parameters?" (NOT "Does pagination work?")
- "Does the spec declare filter operators?" (NOT "Does filtering work correctly?")
- "Does the response schema have required fields?" (NOT "Does the endpoint return those fields?")

Runtime behavior (does it actually sort/filter/paginate correctly?) is the
responsibility of each endpoint's integration/functional tests.

Scope:
- ✓ OpenAPI spec structure and parameter declarations
- ✓ Response schema definitions
- ✗ Actual endpoint behavior or responses
- ✗ Functional correctness of sorting/filtering/pagination

Standards Reference:
    docs/standards/api-response-format.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.utils.filters import FilterOperator
from tests.unit.api.compliance.conftest import (
    MIN_EXCLUSION_REASON_LENGTH,
    check_passes,
    get_operation,
)
from tests.unit.api.compliance.endpoint_discovery import (
    discover_list_endpoints,
    discover_testable_list_endpoints,
    load_exclusions,
)

if TYPE_CHECKING:
    from tests.unit.api.compliance.endpoint_discovery import EndpointInfo


@pytest.mark.unit
@pytest.mark.compliance
@pytest.mark.parametrize("endpoint", discover_testable_list_endpoints(), ids=lambda e: e.operation_id)
class TestListEndpointCompliance:
    """Compliance tests for list endpoint standards.

    Tests validate that all list endpoints conform to pagination, filtering,
    and sorting standards by checking OpenAPI spec structure.
    """

    def _get_parameters(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]) -> list[Any]:
        """Get parameters list from OpenAPI spec for the given endpoint."""
        operation = get_operation(endpoint, openapi_spec)
        return operation.get("parameters", [])  # type: ignore[no-any-return]

    def _get_request_body_properties(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]) -> dict[str, Any]:
        """Get request body schema properties for a POST endpoint.

        Resolves the $ref in requestBody to get the schema properties.
        """
        operation = get_operation(endpoint, openapi_spec)
        request_body = operation.get("requestBody", {})
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})

        ref = schema.get("$ref", "")
        if ref:
            schema_name = ref.split("/")[-1]
            schemas: dict[str, Any] = openapi_spec.get("components", {}).get("schemas", {})
            resolved: dict[str, Any] = schemas.get(schema_name, {})
            return dict(resolved.get("properties", {}))
        return dict(schema.get("properties", {}))

    def _get_endpoint_fields(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]) -> dict[str, Any]:
        """Get all declared fields as {name: schema} regardless of HTTP method.

        For POST endpoints, returns request body properties.
        For GET endpoints, returns query parameter schemas (excluding path params).
        """
        if endpoint.method.upper() == "POST":
            return self._get_request_body_properties(endpoint, openapi_spec)
        params = self._get_parameters(endpoint, openapi_spec)
        return {
            p["name"]: p.get("schema", {})
            for p in params
            if isinstance(p, dict) and "name" in p and p.get("in") != "path"
        }

    def test_response_declares_pagination_fields(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]):
        """Validates response schema declares all pagination fields.

        Validates that the response schema declares all fields from ResourcesResponse[T]:
        - resources, next, prev, total
        """
        # Get response schema from components
        schemas = openapi_spec.get("components", {}).get("schemas", {})
        response_schema = schemas.get(endpoint.response_type, {})
        properties = response_schema.get("properties", {})

        # Get required fields from the actual ResourcesResponse model
        # ResourcesResponse inherits from ResourcesResponseBase, so model_fields includes all fields
        required_fields = set(ResourcesResponse.model_fields.keys())

        # Check for all required ResourcesResponse fields (strict validation)
        # Require direct properties to avoid false positives from unrelated allOf inheritance
        for field_name in required_fields:
            assert field_name in properties, f"{endpoint.operation_id} response missing '{field_name}' field"

    def test_declares_pagination_parameters(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]):
        """Validates endpoint declares standard pagination parameters.

        For GET endpoints, checks query parameters.
        For POST endpoints, checks request body schema properties.
        """
        required_pagination_fields = set(BaseListParams.model_fields.keys())

        if endpoint.method.upper() == "POST":
            body_properties = self._get_request_body_properties(endpoint, openapi_spec)
            for field_name in required_pagination_fields:
                assert field_name in body_properties, (
                    f"{endpoint.operation_id} request body missing '{field_name}' property"
                )
            return

        params = self._get_parameters(endpoint, openapi_spec)

        # Collect parameter names and refs
        param_names = set()
        param_refs = set()
        for param in params:
            if isinstance(param, dict):
                if "name" in param:
                    param_names.add(param["name"])
                if "$ref" in param:
                    param_refs.add(param["$ref"])

        # Derive expected OpenAPI $ref names from field names (snake_case → camelCase + "Param")
        def _to_param_ref(field_name: str) -> str:
            parts = field_name.split("_")
            return parts[0] + "".join(p.capitalize() for p in parts[1:]) + "Param"

        for field_name in required_pagination_fields:
            param_ref_name = _to_param_ref(field_name)
            has_param = field_name in param_names or any(param_ref_name in ref for ref in param_refs)
            assert has_param, f"{endpoint.operation_id} missing '{field_name}' parameter"

    def test_sort_parameter_constrains_values(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]):
        """Validates sort parameter schema has enum or pattern constraint.

        The sort parameter should not accept arbitrary strings. At minimum,
        it should declare allowed values via enum or constrain the format
        via a pattern (e.g., ``^-?[a-z][a-z0-9_]*$``).
        """
        fields = self._get_endpoint_fields(endpoint, openapi_spec)
        sort_schema = fields.get("sort", {})

        if not sort_schema:
            pytest.skip("No sort parameter found (covered by test_declares_pagination_parameters)")

        has_constraint = "enum" in sort_schema or "pattern" in sort_schema

        if not has_constraint:
            for item in sort_schema.get("anyOf", []):
                if isinstance(item, dict) and item.get("type") == "string" and ("enum" in item or "pattern" in item):
                    has_constraint = True
                    break

        assert has_constraint, (
            f"{endpoint.operation_id} sort parameter lacks value constraints. "
            f"Schema should declare 'enum' (listing allowed sort fields) or "
            f"'pattern' (constraining the format, e.g., '^-?[a-z][a-z0-9_]*$')"
        )

    @staticmethod
    def _classify_schema(schema: dict[str, Any]) -> str | None:
        """Classify a single schema object by its effective type for operator inference."""
        if schema.get("format") == "date-time":
            return "datetime"
        if schema.get("format") == "uuid" or schema.get("type") == "boolean" or "enum" in schema:
            return "eq_only"
        if schema.get("type") == "string":
            return "string"
        return None

    @staticmethod
    def _infer_required_operators(schema: dict[str, Any]) -> set[str]:
        """Infer minimum required filter operators from a parameter's schema type."""
        all_ops = {op.value for op in FilterOperator}
        comparison_ops = all_ops - {
            FilterOperator.CONTAINS.value,
            FilterOperator.STARTS_WITH.value,
        }
        eq_only = {FilterOperator.EQ.value}
        type_map = {"datetime": comparison_ops, "eq_only": eq_only, "string": all_ops}

        classification = TestListEndpointCompliance._classify_schema(schema)
        if classification is not None:
            return type_map[classification]

        for variant in schema.get("anyOf", []):
            if isinstance(variant, dict):
                classification = TestListEndpointCompliance._classify_schema(variant)
                if classification is not None:
                    return type_map[classification]

        return eq_only

    def _check_filter_operators(
        self,
        endpoint: EndpointInfo,
        field_name: str,
        schema: dict[str, Any],
        required_operators: set[str],
    ) -> None:
        """Validate that a filter field schema declares required operators via allOf."""
        if "allOf" not in schema:
            pytest.fail(
                f"{endpoint.operation_id} parameter '{field_name}' should use allOf schema "
                f"with filter operators {required_operators}"
            )

        all_of = schema.get("allOf", [])
        operator_schemas = [item for item in all_of if item.get("type") == "object"]

        if not operator_schemas:
            pytest.fail(
                f"{endpoint.operation_id} parameter '{field_name}' allOf schema missing "
                f"object type with filter operators"
            )

        declared_operators: set[str] = set()
        for obj_schema in operator_schemas:
            declared_operators.update(obj_schema.get("properties", {}).keys())

        missing_operators = required_operators - declared_operators
        if missing_operators:
            pytest.fail(
                f"{endpoint.operation_id} parameter '{field_name}' missing filter operators: "
                f"{missing_operators}. Should declare: {required_operators}"
            )

    def test_filterable_fields_declare_operators(self, endpoint: EndpointInfo, openapi_spec: dict[str, Any]):
        """Validates filterable fields declare appropriate filter operators.

        Dynamically discovers filter parameters from the OpenAPI spec (any query
        parameter that is not a pagination or path parameter) and validates that
        each one declares the minimum required operators via an allOf schema.

        Minimum required operators are inferred from the parameter's schema type:
        - DateTime fields: eq, gt, gte, lt, lte
        - String fields: eq, contains, starts_with, gt, gte, lt, lte
        - Boolean/enum/UUID fields: eq only

        Endpoints may declare additional operators beyond the minimum.
        """
        pagination_fields = set(BaseListParams.model_fields.keys())
        all_fields = self._get_endpoint_fields(endpoint, openapi_spec)
        filter_fields = {
            name: schema
            for name, schema in all_fields.items()
            if name not in pagination_fields and not schema.get("x-query-param")
        }

        if not filter_fields:
            pytest.skip(f"{endpoint.operation_id} has no filter parameters")

        for field_name, schema in filter_fields.items():
            required_operators = self._infer_required_operators(schema)
            self._check_filter_operators(
                endpoint,
                field_name,
                schema,
                required_operators,
            )


@pytest.mark.unit
@pytest.mark.compliance
class TestExclusionListMaintenance:
    """Tests to ensure the exclusions list stays up-to-date and accurate.

    These tests prevent stale exclusions by validating:
    1. All exclusions have meaningful justifications
    2. All exclusions reference endpoints that still exist
    3. All excluded endpoints are still actually non-compliant
    """

    @pytest.fixture(scope="class")
    def exclusions_list(self):
        """Load exclusions list once for all tests in this class."""
        exclusions_data = load_exclusions()
        return exclusions_data.get("exclusions", [])

    @pytest.fixture(scope="class")
    def excluded_operation_ids(self, exclusions_list):
        """Extract set of excluded operation IDs."""
        return {exc["operation_id"] for exc in exclusions_list}

    @pytest.fixture(scope="class")
    def all_list_endpoints(self):
        """Load all list endpoints once for all tests in this class."""
        return discover_list_endpoints()

    @pytest.fixture(scope="class")
    def all_operation_ids(self, all_list_endpoints):
        """Extract set of all operation IDs."""
        return {ep.operation_id for ep in all_list_endpoints}

    def test_exclusions_have_justifications(self, exclusions_list):
        """Validates all exclusions have meaningful justification."""
        for exc in exclusions_list:
            operation_id = exc.get("operation_id")
            reason = exc.get("reason", "").strip()

            assert operation_id, "Exclusion missing 'operation_id'"
            assert reason, f"Exclusion '{operation_id}' missing 'reason'"
            assert len(reason) >= MIN_EXCLUSION_REASON_LENGTH, (
                f"Exclusion '{operation_id}' reason too brief (min {MIN_EXCLUSION_REASON_LENGTH} chars): {reason}"
            )

    def test_exclusions_reference_existing_endpoints(self, excluded_operation_ids, all_operation_ids):
        """Validates that all exclusions reference endpoints that exist.

        This prevents stale exclusions (e.g. removed endpoints).
        """
        # Find exclusions that reference non-existent endpoints
        missing_endpoints = excluded_operation_ids - all_operation_ids

        if missing_endpoints:
            pytest.fail(
                f"The following exclusions reference endpoints that do not exist: "
                f"{', '.join(sorted(missing_endpoints))}"
            )

    def test_excluded_endpoints_are_still_noncompliant(self, openapi_spec, excluded_operation_ids, all_list_endpoints):
        """Validates that excluded endpoints are still non-compliant.

        This prevents stale exclusions - if an endpoint becomes compliant,
        we should remove it from the exclusions list.

        Checks that each excluded endpoint still fails at least one compliance check.
        If an endpoint passes all checks, it should be removed from exclusions.
        """
        # Filter to just the excluded endpoints
        excluded_endpoints = [ep for ep in all_list_endpoints if ep.operation_id in excluded_operation_ids]

        # Track which excluded endpoints are now compliant
        compliant_excluded = []

        # Instantiate test class to reuse its methods
        test_instance = TestListEndpointCompliance()

        # Define all compliance checks to run
        compliance_checks = [
            test_instance.test_response_declares_pagination_fields,
            test_instance.test_declares_pagination_parameters,
            test_instance.test_sort_parameter_constrains_values,
            test_instance.test_filterable_fields_declare_operators,
        ]

        for endpoint in excluded_endpoints:
            # Run all compliance checks against this endpoint
            # If ALL checks pass, this endpoint is now compliant and should be removed from exclusions
            checks_failed = sum(1 for check in compliance_checks if not check_passes(check, endpoint, openapi_spec))

            # If all checks passed (no failures), this exclusion is stale
            if checks_failed == 0:
                compliant_excluded.append(endpoint.operation_id)

        # Assert that no excluded endpoints are now compliant
        if compliant_excluded:
            pytest.fail(
                f"The following excluded endpoints are now compliant and should be removed from exclusions: "
                f"{', '.join(compliant_excluded)}"
            )
