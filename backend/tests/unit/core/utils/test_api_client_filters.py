"""Unit tests for filter utilities."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from syntara_api_client import OPERATORS as OPERATORS_FROM_PACKAGE
from syntara_api_client.filters import OPERATORS, FilterError, build_filters


class TestPublicAPI:
    """Test public API exports."""

    def test_operators_constant_exported(self) -> None:
        """OPERATORS constant is exported from package root."""
        assert OPERATORS_FROM_PACKAGE == OPERATORS
        assert {"eq", "contains", "starts_with", "gt", "gte", "lt", "lte"} == OPERATORS

    def test_operators_is_set(self) -> None:
        """OPERATORS is a set for efficient membership testing."""
        assert isinstance(OPERATORS, set)


class TestBuildFilters:
    """Test build_filters function."""

    def test_exact_match_no_operator(self) -> None:
        """Field without operator means exact match."""
        result = build_filters(name="exact-name")
        assert result == {"name": "exact-name"}

    def test_exact_match_with_eq_operator(self) -> None:
        """Field with __eq operator is same as no operator."""
        result = build_filters(name__eq="exact-name")
        assert result == {"name": "exact-name"}

    def test_contains_operator(self) -> None:
        """Field with __contains operator."""
        result = build_filters(name__contains="auth")
        assert result == {"name[contains]": "auth"}

    def test_starts_with_operator(self) -> None:
        """Field with __starts_with operator."""
        result = build_filters(name__starts_with="prefix")
        assert result == {"name[starts_with]": "prefix"}

    def test_comparison_operators(self) -> None:
        """Test gt, gte, lt, lte operators."""
        result = build_filters(
            count__gt=10,
            count__gte=5,
            count__lt=100,
            count__lte=99,
        )
        assert result == {
            "count[gt]": "10",
            "count[gte]": "5",
            "count[lt]": "100",
            "count[lte]": "99",
        }

    def test_label_filtering(self) -> None:
        """Label filtering with labels__ prefix."""
        result = build_filters(
            labels__environment="production",
            labels__team="platform",
        )
        assert result == {
            "labels[environment]": "production",
            "labels[team]": "platform",
        }

    def test_empty_label_key_raises_error(self) -> None:
        """Empty label key should raise FilterError."""
        with pytest.raises(FilterError, match="missing label key"):
            build_filters(labels__="value")

    def test_boolean_serialization(self) -> None:
        """Boolean values convert to lowercase strings."""
        result = build_filters(is_enabled=True, is_archived=False)
        assert result == {"is_enabled": "true", "is_archived": "false"}

    def test_datetime_serialization(self) -> None:
        """Datetime objects convert to ISO 8601."""
        dt = datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC)
        result = build_filters(created_at__gte=dt)
        assert result == {"created_at[gte]": "2025-01-15T10:30:45+00:00"}

    def test_date_serialization(self) -> None:
        """Date objects convert to ISO 8601."""
        d = date(2025, 1, 15)
        result = build_filters(created_at__gte=d)
        assert result == {"created_at[gte]": "2025-01-15"}

    def test_uuid_serialization(self) -> None:
        """UUID objects convert to strings."""
        uid = uuid4()
        result = build_filters(created_by=uid)
        assert result == {"created_by": str(uid)}

    def test_none_values_skipped(self) -> None:
        """None values are not included in result."""
        result = build_filters(name="test", description=None)
        assert result == {"name": "test"}
        assert "description" not in result

    def test_invalid_operator_raises_error(self) -> None:
        """Invalid operator raises FilterError."""
        with pytest.raises(FilterError, match="Invalid operator 'invalid'"):
            build_filters(name__invalid="value")

    def test_too_many_parts_raises_error(self) -> None:
        """Too many __ parts raises FilterError."""
        with pytest.raises(FilterError, match="Invalid filter syntax"):
            build_filters(name__contains__extra="value")

    def test_multiple_filters_combined(self) -> None:
        """Multiple filters in single call."""
        result = build_filters(
            name__contains="workflow",
            is_enabled=True,
            created_at__gte="2025-01-01",
            labels__env="prod",
        )
        assert result == {
            "name[contains]": "workflow",
            "is_enabled": "true",
            "created_at[gte]": "2025-01-01",
            "labels[env]": "prod",
        }

    def test_empty_filters(self) -> None:
        """No arguments returns empty dict."""
        result = build_filters()
        assert result == {}


class TestEdgeCasesFieldNames:
    """Test edge cases in field names."""

    def test_field_name_with_dots(self) -> None:
        """Field names with dots are preserved."""
        result = build_filters(**{"metadata.version__eq": "1.0"})
        assert result == {"metadata.version": "1.0"}

    def test_field_name_with_dashes(self) -> None:
        """Field names with dashes are preserved."""
        result = build_filters(**{"created-at__gte": "2025-01-01"})
        assert result == {"created-at[gte]": "2025-01-01"}

    def test_field_name_that_looks_like_operator(self) -> None:
        """Field name 'contains' without operator works."""
        result = build_filters(contains="some-value")
        assert result == {"contains": "some-value"}

    def test_field_name_eq_as_field(self) -> None:
        """Field name 'eq' is treated as field, not operator."""
        result = build_filters(eq="equality")
        assert result == {"eq": "equality"}

    def test_very_long_field_name(self) -> None:
        """Very long field names work correctly."""
        long_field = "a" * 200
        result = build_filters(**{f"{long_field}__contains": "value"})
        assert result == {f"{long_field}[contains]": "value"}


class TestEdgeCasesValues:
    """Test edge cases in filter values."""

    def test_empty_string_value(self) -> None:
        """Empty string values are preserved."""
        result = build_filters(name="")
        assert result == {"name": ""}

    def test_whitespace_only_value(self) -> None:
        """Whitespace-only values are preserved."""
        result = build_filters(name="   ")
        assert result == {"name": "   "}

    def test_value_with_quotes(self) -> None:
        """Values with quotes are preserved."""
        result = build_filters(name='test "quoted" value')
        assert result == {"name": 'test "quoted" value'}

    def test_value_with_brackets(self) -> None:
        """Values with brackets are preserved."""
        result = build_filters(name="test[with]brackets")
        assert result == {"name": "test[with]brackets"}

    def test_value_with_newlines(self) -> None:
        """Values with newlines are preserved."""
        result = build_filters(description="line1\nline2")
        assert result == {"description": "line1\nline2"}

    def test_zero_numeric_value(self) -> None:
        """Zero numeric values work correctly."""
        result = build_filters(count__eq=0)
        assert result == {"count": "0"}

    def test_negative_numeric_value(self) -> None:
        """Negative numeric values work correctly."""
        result = build_filters(count__gt=-10)
        assert result == {"count[gt]": "-10"}

    def test_float_value(self) -> None:
        """Float values are converted to strings."""
        result = build_filters(price__gte=99.99)
        assert result == {"price[gte]": "99.99"}

    def test_very_long_string_value(self) -> None:
        """Very long string values work correctly."""
        long_value = "x" * 1000
        result = build_filters(description=long_value)
        assert result == {"description": long_value}


class TestEdgeCasesLabels:
    """Test edge cases in label filtering."""

    def test_label_key_with_dashes(self) -> None:
        """Label keys with dashes work correctly."""
        result = build_filters(**{"labels__my-label": "value"})
        assert result == {"labels[my-label]": "value"}

    def test_label_key_with_dots(self) -> None:
        """Label keys with dots work correctly."""
        result = build_filters(**{"labels__app.kubernetes.io/name": "syntara"})
        assert result == {"labels[app.kubernetes.io/name]": "syntara"}

    def test_label_key_with_underscores(self) -> None:
        """Label keys with underscores work correctly."""
        result = build_filters(labels__my_label="value")
        assert result == {"labels[my_label]": "value"}

    def test_multiple_labels_combined(self) -> None:
        """Multiple label filters can be combined."""
        result = build_filters(
            labels__env="prod",
            labels__team="platform",
            labels__region="us-east",
        )
        assert result == {
            "labels[env]": "prod",
            "labels[team]": "platform",
            "labels[region]": "us-east",
        }


class TestEdgeCasesDatetime:
    """Test edge cases in datetime handling."""

    def test_datetime_with_microseconds(self) -> None:
        """Datetime with microseconds is preserved."""
        dt = datetime(2025, 1, 15, 10, 30, 45, 123456, tzinfo=UTC)
        result = build_filters(created_at=dt)
        assert result == {"created_at": "2025-01-15T10:30:45.123456+00:00"}

    def test_datetime_naive_warning(self) -> None:
        """Naive datetime (no timezone) works but may be ambiguous."""
        # This is allowed but the API might interpret it differently
        # Note: Naive datetimes are discouraged - prefer datetime.now(UTC)
        dt = datetime(2025, 1, 15, 10, 30, 45)  # noqa: DTZ001 - intentionally testing naive datetime
        result = build_filters(created_at=dt)
        assert result == {"created_at": "2025-01-15T10:30:45"}

    def test_date_min_max_values(self) -> None:
        """Min and max date values work correctly."""
        # Just check they don't error - actual values may vary by system
        result = build_filters(
            start_date__gte=date(1, 1, 1),
            end_date__lte=date(9999, 12, 31),
        )
        assert "start_date[gte]" in result
        assert "end_date[lte]" in result


class TestBackwardCompatibility:
    """Test backward compatibility with manual dictionary approach."""

    def test_manual_dict_still_works(self) -> None:
        """The old manual dictionary approach is still valid.

        This demonstrates that build_filters() is purely additive -
        existing code using manual dictionaries continues to work.
        """
        # Old approach - manual dictionary construction
        manual_filters = {
            "name[contains]": "auth",
            "labels[environment]": "production",
            "created_at[gte]": "2025-01-01T00:00:00Z",
        }

        # This is what users pass to additional_params - it's just a dict
        assert isinstance(manual_filters, dict)
        assert manual_filters["name[contains]"] == "auth"

    def test_new_filters_produce_same_output_as_manual(self) -> None:
        """build_filters() produces identical output to manual dictionaries.

        Demonstrates that the new approach is functionally equivalent
        to the old approach - both produce the same dict structure.
        """
        # Old approach - manual dictionary
        manual = {
            "name[contains]": "auth",
            "labels[environment]": "production",
            "created_at[gte]": "2025-01-01",
        }

        # New approach - build_filters
        generated = build_filters(
            name__contains="auth",
            labels__environment="production",
            created_at__gte="2025-01-01",
        )

        # Both produce identical dictionaries
        assert generated == manual

    def test_can_mix_approaches(self) -> None:
        """Can combine manual dicts with build_filters() using dict operations.

        Useful for migrating incrementally - teams can keep some manual
        filters while adopting build_filters() for new code.
        """
        # Some filters built manually (legacy code)
        manual_filters = {"legacy[eq]": "value"}

        # New filters using build_filters
        new_filters = build_filters(name__contains="test")

        # Combine both approaches using standard dict operations
        combined = {**manual_filters, **new_filters}

        assert combined == {
            "legacy[eq]": "value",
            "name[contains]": "test",
        }

    def test_old_approach_example_from_docs(self) -> None:
        """Example from documentation showing old approach still works."""
        # This is the old approach shown in docs - it's still valid
        old_way = {
            "name[contains]": "deploy",
            "is_enabled": "true",
            "labels[team]": "backend",
        }

        # New approach produces the same result
        new_way = build_filters(
            name__contains="deploy",
            is_enabled=True,  # Auto-converts to "true"
            labels__team="backend",
        )

        assert new_way == old_way


class TestDynamicFilterBuilding:
    """Test patterns for building filters dynamically/conditionally."""

    def test_dict_update_pattern(self) -> None:
        """Dynamic filters using dict.update() pattern from docs."""
        filters = build_filters(is_enabled=True)
        assert filters == {"is_enabled": "true"}

        # Add more filters conditionally
        name_search = "workflow"
        if name_search:
            filters.update(build_filters(name__contains=name_search))

        assert filters == {"is_enabled": "true", "name[contains]": "workflow"}

    def test_dict_unpacking_pattern(self) -> None:
        """Combine filters using dict unpacking."""
        base_filters = build_filters(is_enabled=True)
        env_filters = build_filters(labels__environment="prod")

        # Combine using unpacking
        combined = {**base_filters, **env_filters}

        assert combined == {"is_enabled": "true", "labels[environment]": "prod"}

    def test_conditional_filter_building(self) -> None:
        """Build filters conditionally based on user input.

        Demonstrates pattern for building filters when some parameters might be None.
        The specific field names (name, labels__environment, etc.) depend on what
        the endpoint accepts - this is just an example pattern.
        """
        # Simulating user search parameters (some may be None)
        name_search: str | None = "test"
        environment: str | None = "production"
        optional_field: str | None = None  # User didn't specify this optional filter

        # Build base filters
        filters = build_filters(is_enabled=True)

        # Add more conditionally based on user input
        if name_search:
            filters.update(build_filters(name__contains=name_search))
        if environment:
            filters.update(build_filters(labels__environment=environment))
        if optional_field is not None:  # Only add if user specified
            filters.update(build_filters(description__contains=optional_field))

        assert filters == {
            "is_enabled": "true",
            "name[contains]": "test",
            "labels[environment]": "production",
        }

    def test_filter_override_pattern(self) -> None:
        """Later filters override earlier ones using dict.update()."""
        filters = build_filters(name="old_value")
        assert filters == {"name": "old_value"}

        # Override with new value
        filters.update(build_filters(name="new_value"))
        assert filters == {"name": "new_value"}

    def test_combining_multiple_label_filters(self) -> None:
        """Combine multiple label filters dynamically."""
        filters = {}

        labels = {"environment": "prod", "team": "backend", "region": "us-east"}
        for key, value in labels.items():
            filters.update(build_filters(**{f"labels__{key}": value}))

        assert filters == {
            "labels[environment]": "prod",
            "labels[team]": "backend",
            "labels[region]": "us-east",
        }

    def test_filter_builder_function(self) -> None:
        """Create a reusable filter builder function."""

        def build_workflow_filters(
            name: str | None = None,
            *,
            enabled: bool | None = None,
            environment: str | None = None,
        ) -> dict[str, str]:
            """Reusable function to build workflow filters."""
            filters = {}

            if name:
                filters.update(build_filters(name__contains=name))
            if enabled is not None:
                filters.update(build_filters(is_enabled=enabled))
            if environment:
                filters.update(build_filters(labels__environment=environment))

            return filters

        # Use the helper function
        result = build_workflow_filters(name="deploy", enabled=True, environment="prod")

        assert result == {
            "name[contains]": "deploy",
            "is_enabled": "true",
            "labels[environment]": "prod",
        }

    def test_empty_filters_dict(self) -> None:
        """Empty filters dict when all values are None."""
        filters = build_filters(
            name=None,
            is_enabled=None,
            count=None,
        )
        assert filters == {}

    def test_build_all_operators_in_one_call(self) -> None:
        """Build filters with all operators in single call."""
        filters = build_filters(
            name__eq="exact",
            description__contains="text",
            title__starts_with="prefix",
            count__gt=10,
            count__gte=5,
            price__lt=100,
            price__lte=99,
            labels__environment="prod",
        )

        assert filters == {
            "name": "exact",
            "description[contains]": "text",
            "title[starts_with]": "prefix",
            "count[gt]": "10",
            "count[gte]": "5",
            "price[lt]": "100",
            "price[lte]": "99",
            "labels[environment]": "prod",
        }
