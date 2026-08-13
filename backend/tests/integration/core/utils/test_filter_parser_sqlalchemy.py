"""Unit tests for FilterParser SQLAlchemy Query API functionality.

These tests verify that FilterParser can correctly apply filters to SQLAlchemy Query objects
using the query.filter() API instead of building raw SQL strings.
"""
# ruff: noqa: DTZ001
# mypy: disable-error-code="arg-type,attr-defined"

from datetime import datetime
from unittest.mock import Mock

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.utils.filters import Filter, FilterOperator, apply_filters, parse_filters


@pytest.mark.asyncio
class TestFilterParserSQLAlchemy:
    """Test FilterParser SQLAlchemy Query API integration."""

    async def test_apply_filters_empty_filters_list(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that empty filters list returns original query unchanged."""
        query = select(User)
        filters: list[Filter] = []

        # Apply filters should return the same query
        filtered_query = apply_filters(query, filters, User)

        # Should be able to execute without changes
        result = (await test_db_session.exec(filtered_query)).all()
        assert len(result) == len(test_users)

    async def test_apply_filters_equality_operator(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test applying equality filter using Query API."""
        query = select(User)
        filters = [Filter(field="username", operator=FilterOperator.EQ, value="alice")]

        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        alice_user = next(u for u in test_users if u.username == "alice")
        assert len(result) == 1
        assert result[0].username == alice_user.username
        assert result[0].email == alice_user.email

    async def test_apply_filters_contains_operator(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test applying contains filter using ilike."""
        query = select(User)
        filters = [Filter(field="first_name", operator=FilterOperator.CONTAINS, value="o")]

        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with 'o' in first_name
        expected_users = [u for u in test_users if "o" in u.first_name.lower()]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_filters_starts_with_operator(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying starts_with filter using ilike."""
        query = select(User)
        filters = [Filter(field="username", operator=FilterOperator.STARTS_WITH, value="b")]

        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users starting with 'b'
        expected_users = [u for u in test_users if u.username.startswith("b")]
        assert len(result) == len(expected_users)
        assert result[0].username == expected_users[0].username

    async def test_apply_filters_datetime_comparison_operators(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying datetime comparison filters."""
        query = select(User)

        # Test greater than Jan 2nd
        filters = [Filter(field="created_at", operator=FilterOperator.GT, value=datetime(2025, 1, 2, 11, 0, 0))]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()
        # Users created after Jan 2nd 11:00
        expected_users = [u for u in test_users if u.created_at > datetime(2025, 1, 2, 11, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test greater than or equal to Jan 2nd
        filters = [Filter(field="created_at", operator=FilterOperator.GTE, value=datetime(2025, 1, 2, 11, 0, 0))]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()
        # Users created on/after Jan 2nd 11:00
        expected_users = [u for u in test_users if u.created_at >= datetime(2025, 1, 2, 11, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test less than Jan 3rd
        filters = [Filter(field="created_at", operator=FilterOperator.LT, value=datetime(2025, 1, 3, 12, 0, 0))]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()
        # Users created before Jan 3rd 12:00
        expected_users = [u for u in test_users if u.created_at < datetime(2025, 1, 3, 12, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test less than or equal to Jan 3rd
        filters = [Filter(field="created_at", operator=FilterOperator.LTE, value=datetime(2025, 1, 3, 12, 0, 0))]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()
        # Users created on/before Jan 3rd 12:00
        expected_users = [u for u in test_users if u.created_at <= datetime(2025, 1, 3, 12, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_filters_boolean_field(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test applying filter to boolean field."""
        query = select(User)
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value=True)]

        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users
        expected_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_filters_multiple_conditions_and_logic(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying multiple filters with AND logic."""
        query = select(User)
        filters = [
            Filter(field="is_enabled", operator=FilterOperator.EQ, value=True),
            Filter(field="created_at", operator=FilterOperator.GTE, value=datetime(2025, 1, 2, 11, 0, 0)),
        ]

        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users created on/after Jan 2nd
        expected_users = [u for u in test_users if u.is_enabled and u.created_at >= datetime(2025, 1, 2, 11, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_filters_invalid_field_raises_error(self) -> None:
        """Test that invalid field name raises SafeValueError."""
        query = select(User)
        filters = [Filter(field="nonexistent_field", operator=FilterOperator.EQ, value="test")]

        with pytest.raises(SafeValueError, match="Invalid filter field: nonexistent_field"):
            apply_filters(query, filters, User)

    async def test_apply_filters_with_parsed_filters(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complete workflow: parse parameters and apply to query."""
        # Parse filters from query parameters
        params = {
            "username[starts_with]": "a",
            "is_enabled": "1",  # String representation of boolean
        }
        allowed_fields = ["username", "is_enabled"]
        filters = parse_filters(params, allowed_fields)

        # Convert string "1" to boolean
        for filter_obj in filters:
            if filter_obj.field == "is_enabled":
                filter_obj.value = bool(int(str(filter_obj.value)))

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users starting with 'a' and active
        expected_users = [u for u in test_users if u.username.startswith("a") and u.is_enabled]
        assert len(result) == len(expected_users)
        assert {u.username for u in result} == {u.username for u in expected_users}

    async def test_apply_filters_case_insensitive_string_operations(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that string operations are case-insensitive."""
        query = select(User)

        # Test contains with different case
        filters = [Filter(field="first_name", operator=FilterOperator.CONTAINS, value="ALICE")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        alice_user = next(u for u in test_users if u.username == "alice")
        assert len(result) == 1
        assert result[0].username == alice_user.username

        # Test starts_with with different case
        filters = [Filter(field="username", operator=FilterOperator.STARTS_WITH, value="BOB")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        bob_user = next(u for u in test_users if u.username == "bob")
        assert len(result) == 1
        assert result[0].username == bob_user.username

    async def test_apply_filters_method_signature_and_validation(self) -> None:
        """Test apply_filters method signature and basic validation."""
        # Test that apply_filters function exists and has correct signature
        assert callable(apply_filters)

        # Test that it validates model fields properly
        mock_query = Mock()
        mock_model = Mock(spec=[])  # Empty spec means hasattr returns False for everything
        mock_model.__name__ = "MockModel"

        # Test with invalid field - should raise SafeValueError
        filters = [Filter(field="nonexistent_field", operator=FilterOperator.EQ, value="test")]

        with pytest.raises(SafeValueError, match="Invalid filter field: nonexistent_field"):
            apply_filters(mock_query, filters, mock_model)

        # Test with empty filters - should return original query
        empty_filters: list[Filter] = []
        result = apply_filters(mock_query, empty_filters, mock_model)  # type: ignore[var-annotated]
        assert result == mock_query

    async def test_datetime_field_filtering(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test filtering datetime fields."""
        query = select(User)

        # Test filtering by date (as string, would be converted by your app)
        filters = [Filter(field="created_at", operator=FilterOperator.GTE, value=datetime(2025, 1, 3, 0, 0, 0))]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users created on/after Jan 3
        expected_users = [u for u in test_users if u.created_at >= datetime(2025, 1, 3, 0, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_boolean_string_to_boolean_conversion(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test automatic conversion of boolean string values to actual boolean types."""
        query = select(User)

        # Test "true" string converts to True boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="true")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users
        expected_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test "false" string converts to False boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="false")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match inactive users
        expected_users = [u for u in test_users if not u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_boolean_numeric_string_conversion(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test conversion of numeric string representations to boolean."""
        query = select(User)

        # Test "1" string converts to True boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="1")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users
        expected_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test "0" string converts to False boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="0")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match inactive users
        expected_users = [u for u in test_users if not u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_boolean_alternative_string_representations(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test alternative boolean string representations (yes/no, on/off)."""
        query = select(User)

        # Test "yes" string converts to True boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="yes")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users
        expected_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test "no" string converts to False boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="no")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match inactive users
        expected_users = [u for u in test_users if not u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test "on" string converts to True boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="on")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users
        expected_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test "off" string converts to False boolean
        filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value="off")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match inactive users
        expected_users = [u for u in test_users if not u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_boolean_case_insensitive_conversion(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that boolean string conversion is case-insensitive."""
        query = select(User)

        # Test various case combinations for "true"
        true_variations = ["TRUE", "True", "TrUe", "tRUE"]
        for true_value in true_variations:
            filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value=true_value)]
            filtered_query = apply_filters(query, filters, User)
            result = (await test_db_session.exec(filtered_query)).all()

            # Should match active users
            expected_users = [u for u in test_users if u.is_enabled]
            assert len(result) == len(expected_users)
            usernames = {user.username for user in result}
            expected_usernames = {u.username for u in expected_users}
            assert usernames == expected_usernames

        # Test various case combinations for "false"
        false_variations = ["FALSE", "False", "FaLsE", "fALSE"]
        for false_value in false_variations:
            filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value=false_value)]
            filtered_query = apply_filters(query, filters, User)
            result = (await test_db_session.exec(filtered_query)).all()

            # Should match inactive users
            expected_users = [u for u in test_users if not u.is_enabled]
            assert len(result) == len(expected_users)
            usernames = {user.username for user in result}
            expected_usernames = {u.username for u in expected_users}
            assert usernames == expected_usernames

    async def test_boolean_invalid_string_raises_error(self) -> None:
        """Test that invalid boolean strings raise SafeValueError."""
        query = select(User)

        # Test invalid boolean strings
        invalid_values = ["invalid", "maybe", "sometimes", "2", "-1", "null", ""]

        for invalid_value in invalid_values:
            filters = [Filter(field="is_enabled", operator=FilterOperator.EQ, value=invalid_value)]

            with pytest.raises(SafeValueError, match="Invalid boolean value"):
                apply_filters(query, filters, User)

    async def test_end_to_end_boolean_filtering_from_query_params(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complete workflow: parse boolean query parameters and apply filters."""
        # Test the exact scenario that was failing: enabled[eq]=false
        params = {"is_enabled[eq]": "false"}
        allowed_fields = ["is_enabled"]

        # Parse filters from query parameters
        filters = parse_filters(params, allowed_fields)

        # Apply to query - this should automatically convert "false" to False
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match inactive users
        expected_users = [u for u in test_users if not u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames
        for user in result:
            assert user.is_enabled is False

        # Test the opposite: enabled[eq]=true
        params = {"is_enabled[eq]": "true"}
        filters = parse_filters(params, allowed_fields)

        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users
        expected_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames
        for user in result:
            assert user.is_enabled is True

    async def test_boolean_filtering_mixed_with_other_filters(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test boolean filtering combined with other filter types."""
        # Test boolean + datetime filter
        params = {"is_enabled[eq]": "true", "created_at[gte]": "2025-01-02T11:00:00"}
        allowed_fields = ["is_enabled", "created_at"]
        filters = parse_filters(params, allowed_fields)

        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match active users created on/after Jan 2nd
        expected_users = [u for u in test_users if u.is_enabled and u.created_at >= datetime(2025, 1, 2, 11, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

        # Test boolean + string filter
        params = {"is_enabled[eq]": "false", "username[starts_with]": "c"}
        allowed_fields = ["is_enabled", "username"]
        filters = parse_filters(params, allowed_fields)

        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match inactive users whose username starts with 'c'
        expected_users = [u for u in test_users if not u.is_enabled and u.username.startswith("c")]
        assert len(result) == len(expected_users)
        assert result[0].username == expected_users[0].username
        assert result[0].is_enabled is False


@pytest.mark.asyncio
class TestIsNullFiltering:
    """Test ISNULL operator for null/not-null field checks."""

    async def test_isnull_true_filters_to_null_rows(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """``field[isnull]=true`` generates IS NULL and excludes rows with values."""
        query = select(User)
        filters = [Filter(field="last_name", operator=FilterOperator.ISNULL, value="true")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        expected = [u for u in test_users if u.last_name is None]
        assert len(result) == len(expected)

    async def test_isnull_false_filters_to_non_null_rows(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """``field[isnull]=false`` generates IS NOT NULL and returns rows with values."""
        query = select(User)
        filters = [Filter(field="last_name", operator=FilterOperator.ISNULL, value="false")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        expected = [u for u in test_users if u.last_name is not None]
        assert len(result) == len(expected)
        assert {u.username for u in result} == {u.username for u in expected}

    async def test_isnull_combined_with_equality_filter(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """ISNULL composes with other operators via AND."""
        query = select(User)
        filters = [
            Filter(field="last_name", operator=FilterOperator.ISNULL, value="false"),
            Filter(field="is_enabled", operator=FilterOperator.EQ, value="true"),
        ]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        expected = [u for u in test_users if u.last_name is not None and u.is_enabled]
        assert len(result) == len(expected)
        assert {u.username for u in result} == {u.username for u in expected}

    async def test_isnull_end_to_end_from_query_params(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """End-to-end: parse ``?last_name[isnull]=false`` and apply to query."""
        params = {"last_name[isnull]": "false"}
        filters = parse_filters(params, ["last_name"])

        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.ISNULL

        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        expected = [u for u in test_users if u.last_name is not None]
        assert len(result) == len(expected)

    async def test_isnull_accepts_boolean_string_variants(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """ISNULL accepts all boolean string variants (1, yes, on, etc.)."""
        query = select(User)
        non_null_count = len([u for u in test_users if u.last_name is not None])

        for false_variant in ("false", "0", "no", "off", "False", "FALSE"):
            filters = [Filter(field="last_name", operator=FilterOperator.ISNULL, value=false_variant)]
            filtered_query = apply_filters(query, filters, User)
            result = (await test_db_session.exec(filtered_query)).all()
            assert len(result) == non_null_count, f"Failed for isnull={false_variant}"

    async def test_isnull_invalid_value_raises_error(self) -> None:
        """ISNULL with a non-boolean string raises SafeValueError."""
        query = select(User)
        filters = [Filter(field="last_name", operator=FilterOperator.ISNULL, value="maybe")]

        with pytest.raises(SafeValueError, match="Invalid boolean value"):
            apply_filters(query, filters, User)


@pytest.mark.asyncio
class TestSQLInjectionProtection:
    """Test SQL injection protection in filter operations with real database."""

    async def test_like_injection_protection_contains(self, test_db_session: AsyncSession) -> None:
        """Test that LIKE injection attempts are properly sanitized with contains operator."""
        query = select(User)

        # Test SQL injection attempts through contains operator
        injection_attempts = [
            "%'; DROP TABLE users; --",  # Classic injection with wildcard
            "_' OR '1'='1",  # Injection with underscore wildcard
            "\\'; DELETE FROM users; --",  # Injection with escaped characters
            "%' UNION SELECT * FROM passwords --",  # Union-based injection
        ]

        for injection_value in injection_attempts:
            filters = [Filter(field="first_name", operator=FilterOperator.CONTAINS, value=injection_value)]
            filtered_query = apply_filters(query, filters, User)

            # Should execute safely without SQL injection
            result = (await test_db_session.exec(filtered_query)).all()

            # Should return empty result since no user has these exact escaped values
            assert len(result) == 0

    async def test_like_injection_protection_starts_with(self, test_db_session: AsyncSession) -> None:
        """Test that LIKE injection attempts are properly sanitized with starts_with operator."""
        query = select(User)

        # Test injection attempts through starts_with operator
        injection_attempts = [
            "Alice%'; DROP TABLE--",  # Injection after legitimate start
            "_lice' OR 1=1--",  # Wildcard injection
            "\\' OR 'a'='a",  # Boolean injection
        ]

        for injection_value in injection_attempts:
            filters = [Filter(field="first_name", operator=FilterOperator.STARTS_WITH, value=injection_value)]
            filtered_query = apply_filters(query, filters, User)

            # Should execute safely without SQL injection
            result = (await test_db_session.exec(filtered_query)).all()

            # Should return empty result since wildcards are escaped
            assert len(result) == 0

    async def test_wildcard_escaping_functionality(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test that wildcards are properly escaped but filtering still works correctly."""
        query = select(User)

        # Test that % wildcard is escaped in contains
        filters = [Filter(field="username", operator=FilterOperator.CONTAINS, value="ali%ce")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should not match "alice" because % is escaped to literal %
        assert len(result) == 0

        # Test that _ wildcard is escaped in contains
        filters = [Filter(field="username", operator=FilterOperator.CONTAINS, value="alic_")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should not match "alice" because _ is escaped to literal _
        assert len(result) == 0

        # Test normal contains still works
        filters = [Filter(field="username", operator=FilterOperator.CONTAINS, value="lic")]
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match "alice" because no wildcards to escape
        alice_user = next(u for u in test_users if u.username == "alice")
        assert len(result) == 1
        assert result[0].username == alice_user.username

    async def test_backslash_escaping_in_filters(self, test_db_session: AsyncSession) -> None:
        """Test proper handling of backslashes in filter values."""
        query = select(User)

        # Test various backslash patterns
        backslash_patterns = [
            "test\\value",  # Single backslash
            "test\\\\value",  # Double backslash
            "\\%test",  # Backslash with wildcard
            "\\_test",  # Backslash with underscore
        ]

        for pattern in backslash_patterns:
            filters = [Filter(field="username", operator=FilterOperator.CONTAINS, value=pattern)]
            filtered_query = apply_filters(query, filters, User)

            # Should execute safely without error
            result = (await test_db_session.exec(filtered_query)).all()
            # Should return empty since no users have these patterns in username
            assert len(result) == 0

    async def test_injection_through_field_values_with_special_chars(self, test_db_session: AsyncSession) -> None:
        """Test injection attempts through special characters in field values."""
        query = select(User)

        # Test various special character injection attempts
        special_char_injections = [
            "'; CREATE TABLE malicious (id INT); --",
            "' AND 1=1--",
            "' UNION ALL SELECT NULL--",
            "'; INSERT INTO users (username) VALUES ('hacker'); --",
            "' OR username LIKE '%'--",
        ]

        for injection_value in special_char_injections:
            # Test with different operators to ensure all are protected
            for operator in [FilterOperator.EQ, FilterOperator.CONTAINS, FilterOperator.STARTS_WITH]:
                filters = [Filter(field="username", operator=operator, value=injection_value)]
                filtered_query = apply_filters(query, filters, User)

                # Should execute safely without SQL injection
                result = (await test_db_session.exec(filtered_query)).all()

                # Should not find any matches for these injection strings
                assert len(result) == 0

    async def test_parametrized_query_protection(self, test_db_session: AsyncSession) -> None:
        """Test that SQLAlchemy's parametrized queries protect against injection."""
        query = select(User)

        # Test that SQLAlchemy correctly parameterizes our filter values
        # This is more of a verification that our approach is sound
        dangerous_value = "'; DROP TABLE users; SELECT * FROM users WHERE username='"

        filters = [Filter(field="username", operator=FilterOperator.EQ, value=dangerous_value)]
        filtered_query = apply_filters(query, filters, User)

        # The query should be safely parameterized - we can inspect it
        # SQLAlchemy should use bound parameters, not string concatenation
        compiled_query = filtered_query.compile(compile_kwargs={"literal_binds": False})

        # Should contain parameter placeholders, not the literal dangerous value
        query_str = str(compiled_query)
        assert dangerous_value not in query_str
        assert ":username_1" in query_str or "%(username_1)s" in query_str or "?" in query_str

        # Execute safely
        result = (await test_db_session.exec(filtered_query)).all()
        assert len(result) == 0

    async def test_multiple_injection_attempts_combined(self, test_db_session: AsyncSession) -> None:
        """Test multiple simultaneous injection attempts in different fields."""
        query = select(User)

        # Combine multiple injection attempts in one filter set
        filters = [
            Filter(field="username", operator=FilterOperator.CONTAINS, value="'; DROP TABLE--"),
            Filter(field="first_name", operator=FilterOperator.STARTS_WITH, value="%' OR 1=1--"),
            Filter(field="email", operator=FilterOperator.EQ, value="' UNION SELECT--"),
        ]

        filtered_query = apply_filters(query, filters, User)

        # Should execute safely without any SQL injection
        result = (await test_db_session.exec(filtered_query)).all()

        # Should return empty result since no user matches these injection strings
        assert len(result) == 0

    async def test_case_insensitive_operations_with_injection(self, test_db_session: AsyncSession) -> None:
        """Test that case-insensitive operations don't introduce injection vulnerabilities."""
        query = select(User)

        # Test injection attempts with case variations
        case_injection_attempts = [
            "Alice'; DROP table USERS;--",
            "ALICE%'; delete FROM users;--",
            "alice_' OR '1'='1'--",
        ]

        for injection_value in case_injection_attempts:
            filters = [Filter(field="first_name", operator=FilterOperator.CONTAINS, value=injection_value)]
            filtered_query = apply_filters(query, filters, User)

            # Should execute safely
            result = (await test_db_session.exec(filtered_query)).all()

            # Should not match legitimate users due to escaped wildcards
            assert len(result) == 0


@pytest.mark.asyncio
class TestLogicalORFiltering:
    """Test logical OR functionality with comma-separated values at parser level.

    Note: The current apply_filters implementation uses AND logic between all filters.
    These tests demonstrate the parsing layer's support for OR logic via comma-separated values,
    showing how multiple Filter objects are created for potential OR application.
    """

    async def test_logical_or_with_comma_separated_equality_filters(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test OR logic with comma-separated values for equality filters."""
        # Parse comma-separated username values
        params = {"username": "alice,charlie,eve"}
        allowed_fields = ["username"]
        filters = parse_filters(params, allowed_fields)

        # Should create 3 separate filters for OR logic
        assert len(filters) == 3
        assert all(f.field == "username" for f in filters)
        assert all(f.operator == FilterOperator.EQ for f in filters)

        # Apply to query - should match users with username = 'alice' OR 'charlie' OR 'eve'
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users in the comma-separated list
        target_usernames = ["alice", "charlie", "eve"]
        expected_users = [u for u in test_users if u.username in target_usernames]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_with_bracket_notation_contains(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test OR logic with bracket notation using contains operator."""
        # Parse comma-separated values with contains operator
        params = {"last_name[contains]": "Smith,Johnson,Prince"}
        allowed_fields = ["last_name"]
        filters = parse_filters(params, allowed_fields)

        # Should create 3 separate filters for OR logic
        assert len(filters) == 3
        assert all(f.field == "last_name" for f in filters)
        assert all(f.operator == FilterOperator.CONTAINS for f in filters)

        # Apply to query - should match users whose last_name contains 'Smith' OR 'Johnson' OR 'Prince'
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users whose last_name contains specified values
        contains_values = ["Smith", "Johnson", "Prince"]
        expected_users = [u for u in test_users if u.last_name and any(val in u.last_name for val in contains_values)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_with_datetime_comparison_filters(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test OR logic with datetime comparison operators."""
        # Parse comma-separated created_at values with gte operator
        params = {"created_at[gte]": "2025-01-01T00:00:00,2025-01-03T00:00:00,2025-01-05T00:00:00"}
        allowed_fields = ["created_at"]
        filters = parse_filters(params, allowed_fields)

        # Should create 3 separate filters
        assert len(filters) == 3
        assert all(f.field == "created_at" for f in filters)
        assert all(f.operator == FilterOperator.GTE for f in filters)

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Since it's OR logic with >=, anyone created on/after Jan 1st will match (which is everyone)
        # This demonstrates that OR with overlapping conditions can be broader than expected
        assert len(result) == len(test_users)  # All users created on/after Jan 1st

    async def test_logical_or_with_specific_datetime_conditions(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test OR logic with specific datetime conditions."""
        # Test specific created_at values: created on Jan 1st OR Jan 3rd OR Jan 5th
        params = {"created_at": "2025-01-01T10:00:00,2025-01-03T12:00:00,2025-01-05T14:00:00"}
        allowed_fields = ["created_at"]
        filters = parse_filters(params, allowed_fields)

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users created on specific dates
        expected_datetimes = [
            datetime(2025, 1, 1, 10, 0, 0),
            datetime(2025, 1, 3, 12, 0, 0),
            datetime(2025, 1, 5, 14, 0, 0),
        ]
        expected_users = [u for u in test_users if u.created_at in expected_datetimes]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_with_boolean_values(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test OR logic with boolean values (though OR with boolean is unusual)."""
        # Test is_enabled = true OR = false (which should match everyone)
        params = {"is_enabled": "true,false"}
        allowed_fields = ["is_enabled"]
        filters = parse_filters(params, allowed_fields)

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match all users since everyone is either active or inactive
        assert len(result) == len(test_users)

    async def test_logical_or_mixed_with_and_conditions(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test OR conditions mixed with AND conditions across different fields."""
        # username = 'alice' OR 'bob' OR 'charlie' AND is_enabled = true
        params = {
            "username": "alice,bob,charlie",  # OR logic within username field
            "is_enabled": "true",  # AND logic with is_enabled field
        }
        allowed_fields = ["username", "is_enabled"]
        filters = parse_filters(params, allowed_fields)

        # Should create 4 filters total: 3 for username OR + 1 for is_enabled
        assert len(filters) == 4

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users in username list who are active
        target_usernames = ["alice", "bob", "charlie"]
        expected_users = [u for u in test_users if u.username in target_usernames and u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_with_starts_with_operator(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test OR logic with starts_with operator."""
        # first_name starts_with 'Alice' OR 'Bob' OR 'Eve'
        params = {"first_name[starts_with]": "Alice,Bob,Eve"}
        allowed_fields = ["first_name"]
        filters = parse_filters(params, allowed_fields)

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users whose first_name starts with specified values
        start_values = ["Alice", "Bob", "Eve"]
        expected_users = [u for u in test_users if any(u.first_name.startswith(val) for val in start_values)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_with_whitespace_handling(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that OR logic properly handles whitespace in comma-separated values."""
        # Test with various whitespace patterns
        params = {"username": " alice , bob,  charlie  ,diana"}
        allowed_fields = ["username"]
        filters = parse_filters(params, allowed_fields)

        # Should create 4 filters with trimmed values
        assert len(filters) == 4
        filter_values = {f.value for f in filters}
        assert filter_values == {"alice", "bob", "charlie", "diana"}

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users in the trimmed list
        expected_usernames_list = ["alice", "bob", "charlie", "diana"]
        expected_users = [u for u in test_users if u.username in expected_usernames_list]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_with_datetime_fields(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test OR logic with datetime comparison operators."""
        # created_at >= '2025-01-02' OR >= '2025-01-04' (overlapping conditions)
        params = {"created_at[gte]": "2025-01-02T00:00:00,2025-01-04T00:00:00"}
        allowed_fields = ["created_at"]
        filters = parse_filters(params, allowed_fields)

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users created on/after Jan 2
        expected_users = [u for u in test_users if u.created_at >= datetime(2025, 1, 2, 0, 0, 0)]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_logical_or_complex_multi_field_scenario(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complex scenario with OR logic across multiple fields and operators."""
        # Complex query: (username = 'alice' OR 'eve') AND (created_at >= Jan1 OR >= Jan3) AND is_enabled
        params = {
            "username": "alice,eve",  # OR within username
            "created_at[gte]": "2025-01-01T00:00:00,2025-01-03T00:00:00",  # OR within created_at
            "is_enabled": "true",  # Single condition
        }
        allowed_fields = ["username", "created_at", "is_enabled"]
        filters = parse_filters(params, allowed_fields)

        # Should create 5 filters total: 2 + 2 + 1
        assert len(filters) == 5

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match only alice (username='alice' AND created_at>=Jan1 AND is_enabled=true)
        # eve is excluded because is_enabled=false
        alice_user = next(u for u in test_users if u.username == "alice")
        assert len(result) == 1
        assert result[0].username == alice_user.username

    async def test_logical_or_case_insensitive_operations(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that OR logic works correctly with case-insensitive operations."""
        # Test contains with different cases
        params = {"last_name[contains]": "SMITH,johnson,brown"}
        allowed_fields = ["last_name"]
        filters = parse_filters(params, allowed_fields)

        # Apply to query
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users whose last_name contains specified values (case-insensitive)
        contains_values = ["SMITH", "johnson", "brown"]
        expected_users = [
            u for u in test_users if u.last_name and any(val.lower() in u.last_name.lower() for val in contains_values)
        ]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_end_to_end_or_filtering_workflow(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complete end-to-end workflow with OR filtering from query params to results."""
        # Simulate real API query with multiple OR conditions
        params = {
            "username": "alice,diana",  # Simple OR
            "first_name[starts_with]": "Bob,Charlie",  # Bracket notation OR
            # This creates: (username='alice' OR 'diana') AND (first_name starts_with 'Bob' OR 'Charlie')
        }
        allowed_fields = ["username", "first_name"]

        # Parse filters
        filters = parse_filters(params, allowed_fields)
        assert len(filters) == 4  # 2 + 2

        # Apply filters
        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should find no matches because no user satisfies both conditions:
        # - alice/diana usernames don't have full names starting with Bob/Charlie
        # - Bob/Charlie full names don't have alice/diana usernames
        assert len(result) == 0

        # Test a more permissive scenario
        params = {
            "username": "alice,bob",  # Users alice and bob
            "is_enabled": "true",  # Both are active
        }
        filters = parse_filters(params, [*allowed_fields, "is_enabled"])

        query = select(User)
        filtered_query = apply_filters(query, filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users in the list who are active
        target_usernames = ["alice", "bob"]
        expected_users = [u for u in test_users if u.username in target_usernames and u.is_enabled]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames


@pytest.mark.asyncio
class TestLogicalINOperator:
    """Test the ``[in]`` operator for multi-value OR filtering."""

    async def test_in_operator_single_value(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """``username[in]=alice`` behaves like a single equality filter."""
        params = {"username[in]": "alice"}
        filters = parse_filters(params, ["username"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        assert len(result) == 1
        assert result[0].username == "alice"

    async def test_in_operator_multiple_values(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """``username[in]=alice,charlie,eve`` returns matching users via OR logic."""
        params = {"username[in]": "alice,charlie,eve"}
        filters = parse_filters(params, ["username"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        target = {"alice", "charlie", "eve"}
        expected = [u for u in test_users if u.username in target]
        assert len(result) == len(expected)
        assert {u.username for u in result} == {u.username for u in expected}

    async def test_in_operator_combined_with_other_field(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """``username[in]=...`` AND ``is_enabled=true`` applies AND between fields."""
        params = {
            "username[in]": "alice,bob,charlie,eve",
            "is_enabled": "true",
        }
        filters = parse_filters(params, ["username", "is_enabled"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        target = {"alice", "bob", "charlie", "eve"}
        expected = [u for u in test_users if u.username in target and u.is_enabled]
        assert len(result) == len(expected)
        assert {u.username for u in result} == {u.username for u in expected}

    async def test_in_operator_with_whitespace(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Whitespace around comma-separated values is trimmed."""
        params = {"username[in]": " alice , bob "}
        filters = parse_filters(params, ["username"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        assert {u.username for u in result} == {"alice", "bob"}

    async def test_in_operator_no_match(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """``username[in]=nonexistent`` returns empty results."""
        params = {"username[in]": "nonexistent,also_nonexistent"}
        filters = parse_filters(params, ["username"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        assert result == []


@pytest.mark.asyncio
class TestLogicalANDFiltering:
    """Test AND semantics when multiple filters target the same field with different operators.

    ``apply_filters`` groups filters by ``(field, operator)`` so comma-separated
    values of the *same* operator OR together, while *different* operators on
    the same field AND together — the composition required for range filters
    like ``?created_at[gte]=X&created_at[lte]=Y``.
    """

    async def test_inclusive_range_on_same_field_uses_and_semantics(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """``created_at[gte]`` + ``created_at[lte]`` selects an inclusive window (AND, not OR).

        Fixture times (see conftest.test_users): alice=Jan1 10:00, bob=Jan2 11:00,
        charlie=Jan3 12:00, diana=Jan4 13:00, eve=Jan5 14:00. Boundaries are chosen
        to cleanly include/exclude whole days.
        """
        params = {
            "created_at[gte]": "2025-01-02T00:00:00",
            "created_at[lte]": "2025-01-04T23:59:59",
        }
        filters = parse_filters(params, ["created_at"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        window = {"bob", "charlie", "diana"}  # Jan 2, 3, 4
        assert {u.username for u in result} == window
        # Users outside the window must be excluded — this is the behaviour
        # that breaks if GTE+LTE on the same field were combined with OR.
        assert "alice" not in {u.username for u in result}  # Jan 1, before window
        assert "eve" not in {u.username for u in result}  # Jan 5, after window

    async def test_exclusive_range_on_same_field_uses_and_semantics(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """``created_at[gt]`` + ``created_at[lt]`` selects an exclusive window."""
        # Strict > Jan 2 end-of-day → excludes bob (Jan 2 11:00); strict < Jan 5 → excludes eve (Jan 5 14:00).
        params = {
            "created_at[gt]": "2025-01-02T23:59:59",
            "created_at[lt]": "2025-01-05T00:00:00",
        }
        filters = parse_filters(params, ["created_at"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        assert {u.username for u in result} == {"charlie", "diana"}

    async def test_half_open_range_on_same_field(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Mixing ``[gte]`` with ``[lt]`` yields a half-open window."""
        params = {
            "created_at[gte]": "2025-01-02T00:00:00",
            "created_at[lt]": "2025-01-05T00:00:00",
        }
        filters = parse_filters(params, ["created_at"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        # [Jan 2, Jan 5) → Jan 2, 3, 4.
        assert {u.username for u in result} == {"bob", "charlie", "diana"}

    async def test_empty_range_returns_no_results(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Lower bound above the upper bound → no rows (confirms AND, not OR)."""
        params = {
            "created_at[gte]": "2025-01-04T00:00:00",
            "created_at[lte]": "2025-01-02T00:00:00",
        }
        filters = parse_filters(params, ["created_at"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        # With the old OR-on-same-field behaviour this would return every row
        # (>=Jan4 OR <=Jan2 covers everyone).  AND-on-different-operators
        # correctly yields an empty set.
        assert result == []

    async def test_string_contains_and_starts_with_same_field_are_anded(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """``first_name[contains]`` + ``first_name[starts_with]`` must AND together."""
        params = {
            "first_name[starts_with]": "A",  # Matches "Alice"
            "first_name[contains]": "lic",  # Also in "Alice"
        }
        filters = parse_filters(params, ["first_name"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        # Only Alice Smith satisfies BOTH: starts with 'A' AND contains 'Smith'.
        assert {u.username for u in result} == {"alice"}

    async def test_range_filter_combines_with_other_field_filter(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """A same-field AND range composes (via AND) with filters on other fields."""
        params = {
            "created_at[gte]": "2025-01-02T00:00:00",
            "created_at[lte]": "2025-01-05T00:00:00",
            "is_enabled": "true",
        }
        filters = parse_filters(params, ["created_at", "is_enabled"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        # Window [Jan 2, Jan 5] → bob, charlie, diana, eve; only active ones → bob, diana.
        assert {u.username for u in result} == {"bob", "diana"}

    async def test_or_within_operator_group_preserved_alongside_and(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Same-operator comma-split values OR together; different operators still AND.

        Regression guard for the grouping fix: the (field, operator) pair is
        the OR boundary, so two values of ``[gt]`` OR but ``[gt]`` and
        ``[lt]`` AND.
        """
        params = {
            # Two GT values → OR within operator group → effectively the lower of the two.
            "created_at[gt]": "2025-01-01T23:59:59,2025-01-03T23:59:59",
            # AND with a separate LT operator.
            "created_at[lt]": "2025-01-05T00:00:00",
        }
        filters = parse_filters(params, ["created_at"])
        # 2 GT + 1 LT = 3 Filter objects.
        assert len(filters) == 3

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        # (created_at > Jan 1 23:59 OR > Jan 3 23:59) AND created_at < Jan 5
        # → created_at > Jan 1 23:59 AND < Jan 5 → bob (Jan 2), charlie (Jan 3), diana (Jan 4).
        assert {u.username for u in result} == {"bob", "charlie", "diana"}

    async def test_three_operators_on_same_field_all_anded(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Three distinct operators on the same field compose via AND."""
        params = {
            "created_at[gte]": "2025-01-02T00:00:00",
            "created_at[lte]": "2025-01-04T23:59:59",
            "created_at[gt]": "2025-01-02T23:59:59",  # Strict > Jan 2 end-of-day → excludes bob.
        }
        filters = parse_filters(params, ["created_at"])

        query = apply_filters(select(User), filters, User)
        result = (await test_db_session.exec(query)).all()

        # GTE Jan 2 AND LTE Jan 4 23:59 AND GT Jan 2 23:59 → Jan 3 and Jan 4 only.
        assert {u.username for u in result} == {"charlie", "diana"}
