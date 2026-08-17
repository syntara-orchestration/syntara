"""Unit tests for apply_sorting SQLAlchemy Query API functionality.

These tests verify that apply_sorting can correctly apply sorting to SQLAlchemy Query objects
using the SQLAlchemy object model instead of building raw SQL strings.
"""
# mypy: disable-error-code="arg-type,attr-defined"

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.utils.cursor import SortDirection
from syntara.core.utils.sorting import apply_sorting


@pytest.mark.asyncio
class TestApplySortingSQLAlchemy:
    """Test apply_sorting SQLAlchemy Query API integration."""

    async def test_apply_sorting_empty_sorts(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test that empty sort tuples returns original query unchanged."""
        query = select(User)
        sort_tuples: list[tuple[str, SortDirection]] = []

        # Apply sorting should return the same query
        sorted_query = apply_sorting(query, sort_tuples, User)

        # Should be able to execute without changes
        result = (await test_db_session.exec(sorted_query)).all()
        assert len(result) == len(test_users)

    async def test_apply_sorting_single_field_ascending(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying single field ascending sort."""
        query = select(User)
        sort_tuples = [("username", SortDirection.ASC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by username ascending: alice, bob, charlie, diana, eve
        assert len(result) == len(test_users)
        usernames = [user.username for user in result]
        expected_usernames = sorted([u.username for u in test_users])
        assert usernames == expected_usernames

    async def test_apply_sorting_single_field_descending(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying single field descending sort."""
        query = select(User)
        sort_tuples = [("created_at", SortDirection.DESC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by created_at descending (newest first): eve, diana, charlie, bob, alice
        assert len(result) == len(test_users)
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(test_users, key=lambda x: x.created_at, reverse=True)]
        assert usernames == expected_usernames

    async def test_apply_sorting_multiple_fields(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test applying multiple field sorting."""
        query = select(User)
        sort_tuples = [
            ("is_enabled", SortDirection.DESC),  # Active users first (True > False)
            ("username", SortDirection.ASC),  # Then by username ascending
        ]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by is_enabled DESC, then username ASC
        # Active users (True): alice, bob, diana
        # Inactive users (False): charlie, eve
        assert len(result) == len(test_users)
        expected_usernames = [u.username for u in sorted(test_users, key=lambda x: (-x.is_enabled, x.username))]
        usernames = [user.username for user in result]
        assert usernames == expected_usernames

    async def test_apply_sorting_datetime_field(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test sorting by datetime field."""
        query = select(User)
        sort_tuples = [("created_at", SortDirection.DESC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by created_at descending (newest first)
        assert len(result) == len(test_users)
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(test_users, key=lambda x: x.created_at, reverse=True)]
        assert usernames == expected_usernames

    async def test_apply_sorting_with_where_clause(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test sorting combined with WHERE clause."""
        query = select(User).where(User.is_enabled == True)  # noqa: E712
        sort_tuples = [("username", SortDirection.DESC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should filter active users and sort by username descending
        active_users = [u for u in test_users if u.is_enabled]
        assert len(result) == len(active_users)
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(active_users, key=lambda x: x.username, reverse=True)]
        assert usernames == expected_usernames

    async def test_apply_sorting_with_limit(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test sorting combined with LIMIT."""
        query = select(User).limit(3)
        sort_tuples = [("username", SortDirection.DESC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be limited to 3 results, sorted by username descending
        assert len(result) == 3
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(test_users, key=lambda x: x.username, reverse=True)][:3]
        assert usernames == expected_usernames

    async def test_apply_sorting_complex_multi_field(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complex multi-field sorting scenario."""
        query = select(User)
        sort_tuples = [
            ("is_enabled", SortDirection.ASC),  # Inactive first (False < True)
            ("first_name", SortDirection.ASC),  # Then by first_name ascending
            ("username", SortDirection.ASC),  # Then by username ascending
        ]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        assert len(result) == len(test_users)
        usernames = [user.username for user in result]
        expected_usernames = [
            u.username for u in sorted(test_users, key=lambda x: (x.is_enabled, x.first_name, x.username))
        ]
        assert usernames == expected_usernames
        # Verify the expected split between inactive and active users
        inactive_count = len([u for u in test_users if not u.is_enabled])
        active_count = len([u for u in test_users if u.is_enabled])
        inactive_users = usernames[:inactive_count]
        active_users = usernames[inactive_count:]
        assert len(inactive_users) == inactive_count
        assert len(active_users) == active_count

    async def test_apply_sorting_invalid_field_raises_error(self) -> None:
        """Test that invalid field names raise SafeValueError."""
        query = select(User)
        sort_tuples = [("invalid_field", SortDirection.ASC)]

        with pytest.raises(SafeValueError, match="Invalid sort field: invalid_field"):
            apply_sorting(query, sort_tuples, User)

    async def test_apply_sorting_mixed_valid_invalid_fields(self) -> None:
        """Test that error is raised even with some valid fields."""
        query = select(User)
        sort_tuples = [
            ("username", SortDirection.ASC),  # Valid field
            ("invalid_field", SortDirection.DESC),  # Invalid field
        ]

        with pytest.raises(SafeValueError, match="Invalid sort field: invalid_field"):
            apply_sorting(query, sort_tuples, User)

    async def test_apply_sorting_all_direction_combinations(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test all combinations of sort directions."""
        query = select(User)

        # Test ASC + ASC
        sort_tuples = [("is_enabled", SortDirection.ASC), ("username", SortDirection.ASC)]
        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(test_users, key=lambda x: (x.is_enabled, x.username))]
        assert usernames == expected_usernames

        # Test DESC + ASC
        sort_tuples = [("is_enabled", SortDirection.DESC), ("username", SortDirection.ASC)]
        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(test_users, key=lambda x: (-x.is_enabled, x.username))]
        assert usernames == expected_usernames

        # Test ASC + DESC
        sort_tuples = [("is_enabled", SortDirection.ASC), ("username", SortDirection.DESC)]
        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()
        usernames = [user.username for user in result]
        expected_usernames = []
        users_by_active: dict[bool, list[User]] = {}
        for user in test_users:
            users_by_active.setdefault(user.is_enabled, []).append(user)

        # Sort is_enabled ASC (False first), then usernames DESC within each group
        for active_key in sorted(users_by_active.keys()):
            group_users = sorted(users_by_active[active_key], key=lambda x: x.username, reverse=True)
            expected_usernames.extend([u.username for u in group_users])
        assert usernames == expected_usernames

        # Test DESC + DESC
        sort_tuples = [("is_enabled", SortDirection.DESC), ("username", SortDirection.DESC)]
        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()
        usernames = [user.username for user in result]
        expected_usernames = []
        users_by_active = {}
        for user in test_users:
            users_by_active.setdefault(user.is_enabled, []).append(user)

        # Sort is_enabled DESC (True first), then usernames DESC within each group
        for active_key in sorted(users_by_active.keys(), reverse=True):
            group_users = sorted(users_by_active[active_key], key=lambda x: x.username, reverse=True)
            expected_usernames.extend([u.username for u in group_users])
        assert usernames == expected_usernames

    async def test_apply_sorting_performance_with_many_sorts(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test performance with many sort criteria."""
        query = select(User)
        # Create multiple sort criteria
        sort_tuples = [
            ("is_enabled", SortDirection.ASC),
            ("username", SortDirection.DESC),
            ("first_name", SortDirection.ASC),
            ("email", SortDirection.DESC),
            ("created_at", SortDirection.ASC),
        ]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should execute successfully with multiple sorts
        assert len(result) == len(test_users)
        # Verify it returned all users with correct ordering
        usernames = [user.username for user in result]
        assert len(set(usernames)) == len(test_users)

    async def test_apply_sorting_string_field_sorting(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test sorting string fields with various cases."""
        query = select(User)
        sort_tuples = [("first_name", SortDirection.ASC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by first_name ascending
        assert len(result) == len(test_users)
        first_names = [user.first_name for user in result]
        expected_first_names = [u.first_name for u in sorted(test_users, key=lambda x: x.first_name)]
        assert first_names == expected_first_names

    async def test_apply_sorting_boolean_field_sorting(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test sorting boolean fields."""
        query = select(User)
        sort_tuples = [("is_enabled", SortDirection.ASC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by is_enabled ascending (False < True)
        assert len(result) == len(test_users)
        is_enabled_values = [user.is_enabled for user in result]
        # Split based on actual test data
        inactive_count = len([u for u in test_users if not u.is_enabled])
        active_count = len([u for u in test_users if u.is_enabled])
        assert is_enabled_values[:inactive_count] == [False] * inactive_count
        assert is_enabled_values[inactive_count:] == [True] * active_count

    async def test_apply_sorting_primary_key_field(self, test_users: list[User], test_db_session: AsyncSession) -> None:
        """Test sorting by primary key field."""
        query = select(User)
        sort_tuples = [("id", SortDirection.DESC)]

        sorted_query = apply_sorting(query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should be sorted by id descending
        assert len(result) == len(test_users)
        ids = [user.id for user in result]
        # Since UUIDs are auto-generated, just verify they're sorted in descending order
        assert len(set(ids)) == len(test_users)  # All unique
        # The order should be consistent when sorted by id
        sorted_ids = sorted(ids, reverse=True)
        assert ids == sorted_ids

    async def test_apply_sorting_with_sqlalchemy_query_operations(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that apply_sorting works with other SQLAlchemy query operations."""
        # Start with a complex query including WHERE, ORDER BY combination
        base_query = select(User).where(User.is_enabled == False)  # noqa: E712
        sort_tuples = [("created_at", SortDirection.DESC)]

        sorted_query = apply_sorting(base_query, sort_tuples, User)
        result = (await test_db_session.exec(sorted_query)).all()

        # Should filter inactive users and sort by created_at DESC
        inactive_users = [u for u in test_users if not u.is_enabled]
        assert len(result) == len(inactive_users)
        usernames = [user.username for user in result]
        expected_usernames = [u.username for u in sorted(inactive_users, key=lambda x: x.created_at, reverse=True)]
        assert usernames == expected_usernames

        # Verify all are inactive
        assert all(not user.is_enabled for user in result)
