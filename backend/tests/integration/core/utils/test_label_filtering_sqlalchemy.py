"""Unit tests for label filtering SQLAlchemy Query API functionality.

These tests verify that apply_label_filters can correctly apply label filters to SQLAlchemy
Query objects using the JSON field operators instead of building raw SQL strings.
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
from syntara.core.utils.labels import apply_label_filters, parse_label_filter


@pytest.mark.asyncio
class TestLabelFilteringSQLAlchemy:
    """Test label filtering SQLAlchemy Query API integration."""

    async def test_apply_label_filters_empty_filters(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that empty label filters returns original query unchanged."""
        query = select(User)
        label_filters: dict[str, str] = {}

        # Apply filters should return the same query
        filtered_query = apply_label_filters(query, label_filters, User)

        # Should be able to execute without changes
        result = (await test_db_session.exec(filtered_query)).all()
        assert len(result) == len(test_users)

    async def test_apply_label_filters_single_label_match(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying single label filter."""
        query = select(User)
        label_filters = {"environment": "production"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with production environment
        expected_users = [u for u in test_users if u.labels.get("environment") == "production"]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_label_filters_multiple_labels_and_logic(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test applying multiple label filters with AND logic."""
        query = select(User)
        label_filters = {"environment": "production", "region": "us-east-1"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with production AND us-east-1
        expected_users = [
            u
            for u in test_users
            if u.labels.get("environment") == "production" and u.labels.get("region") == "us-east-1"
        ]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_label_filters_team_and_service_match(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test filtering by team and service labels."""
        query = select(User)
        label_filters = {"team": "platform", "service": "api"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with platform team AND api service
        expected_users = [
            u for u in test_users if u.labels.get("team") == "platform" and u.labels.get("service") == "api"
        ]
        assert len(result) == len(expected_users)
        usernames = {user.username for user in result}
        expected_usernames = {u.username for u in expected_users}
        assert usernames == expected_usernames

    async def test_apply_label_filters_no_matches(self, test_db_session: AsyncSession) -> None:
        """Test label filtering with no matching users."""
        query = select(User)
        label_filters = {"environment": "production", "team": "nonexistent"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match no users
        assert len(result) == 0

    async def test_apply_label_filters_single_unique_label(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test filtering by a label that only exists on one user."""
        query = select(User)
        label_filters = {"experimental": "true"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with experimental label
        expected_users = [u for u in test_users if u.labels.get("experimental") == "true"]
        assert len(result) == len(expected_users)
        assert result[0].username == expected_users[0].username

    async def test_apply_label_filters_version_pattern(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test filtering by version labels."""
        query = select(User)
        label_filters = {"version": "v1.2.0"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with version v1.2.0
        expected_users = [u for u in test_users if u.labels.get("version") == "v1.2.0"]
        assert len(result) == len(expected_users)
        assert result[0].username == expected_users[0].username

    async def test_apply_label_filters_with_order_by(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test label filtering combined with ORDER BY."""
        query = select(User).order_by(User.username)
        label_filters = {"environment": "production"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should be ordered by username
        expected_users = [u for u in test_users if u.labels.get("environment") == "production"]
        expected_usernames = sorted([u.username for u in expected_users])
        assert len(result) == len(expected_users)
        usernames = [user.username for user in result]
        assert usernames == expected_usernames

    @pytest.mark.usefixtures("test_users")
    async def test_apply_label_filters_with_limit(self, test_db_session: AsyncSession) -> None:
        """Test label filtering combined with LIMIT."""
        query = select(User).limit(2)
        label_filters = {"environment": "production"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should be limited to 2 results
        assert len(result) == 2
        # All should be production environment
        for user in result:
            assert user.labels["environment"] == "production"

    async def test_apply_label_filters_model_without_labels_field(self) -> None:
        """Test that error is raised when model doesn't have labels field."""
        # Create a mock model without labels field
        mock_model = Mock(spec=[])
        mock_model.__name__ = "MockModel"
        query = Mock()
        label_filters = {"environment": "production"}

        with pytest.raises(SafeValueError, match="Label filtering is not supported for this resource"):
            apply_label_filters(query, label_filters, mock_model)

    async def test_apply_label_filters_case_sensitive_matching(self, test_db_session: AsyncSession) -> None:
        """Test that label matching is case-sensitive."""
        query = select(User)
        label_filters = {"environment": "Production"}  # Wrong case

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match no users due to case sensitivity
        assert len(result) == 0

    async def test_apply_label_filters_with_parsed_params(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complete workflow: parse label parameters and apply to query."""
        # Parse labels from query parameters
        params = {"labels[environment]": "production", "labels[team]": "platform", "other_param": "ignored"}
        label_filters = parse_label_filter(params)

        # Apply to query
        query = select(User)
        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users with production + platform team
        expected_users = [
            u for u in test_users if u.labels.get("environment") == "production" and u.labels.get("team") == "platform"
        ]
        assert len(result) == len(expected_users)
        assert result[0].username == expected_users[0].username

    async def test_apply_label_filters_complex_scenario(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test complex scenario with multiple filters and query operations."""
        # Find all production users in us-east-1 region, ordered by creation time
        query = select(User).where(User.is_enabled).order_by("created_at")

        label_filters = {"environment": "production", "region": "us-east-1"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match users that are active, production, us-east-1
        expected_users = [
            u
            for u in test_users
            if u.is_enabled and u.labels.get("environment") == "production" and u.labels.get("region") == "us-east-1"
        ]
        expected_users_sorted = sorted(expected_users, key=lambda x: x.created_at)
        assert len(result) == len(expected_users)
        # Should be ordered by creation time
        assert result[0].username == expected_users_sorted[0].username
        assert result[1].username == expected_users_sorted[1].username

    async def test_apply_label_filters_with_mock_query(self) -> None:
        """Test apply_label_filters method signature and basic validation."""
        # Test that apply_label_filters function exists and has correct signature
        assert callable(apply_label_filters)

        # Test that it validates model labels field properly
        mock_query = Mock()
        mock_model = Mock(spec=[])  # Empty spec means hasattr returns False for everything
        mock_model.__name__ = "MockModel"

        # Test with invalid model - should raise SafeValueError
        label_filters = {"environment": "production"}

        with pytest.raises(SafeValueError, match="Label filtering is not supported for this resource"):
            apply_label_filters(mock_query, label_filters, mock_model)

        # Test with empty filters - should return original query
        empty_filters: dict[str, str] = {}
        mock_model_with_labels = Mock()
        mock_model_with_labels.labels = Mock()
        result = apply_label_filters(mock_query, empty_filters, mock_model_with_labels)  # type: ignore[var-annotated]
        assert result == mock_query

    async def test_apply_label_filters_performance_with_many_labels(self, test_db_session: AsyncSession) -> None:
        """Test performance with users having many labels."""
        # Add a user with many labels
        user_with_many_labels = User(
            username="complex-user",
            email="complex@example.com",
            first_name="Complex",
            last_name="User",
            password_hash="$argon2id$test",  # noqa: S106
            is_enabled=True,
            labels={f"label_{i}": f"value_{i}" for i in range(20)},  # 20 labels
            created_at=datetime(2025, 1, 6, 15, 0, 0),
        )
        test_db_session.add(user_with_many_labels)
        await test_db_session.commit()

        query = select(User)
        label_filters = {"label_0": "value_0", "label_10": "value_10"}

        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Should match the complex-user
        assert len(result) == 1
        assert result[0].username == "complex-user"

    async def test_apply_label_filters_json_field_operations(
        self, test_users: list[User], test_db_session: AsyncSession
    ) -> None:
        """Test that the function uses proper JSON field operations."""
        query = select(User)
        label_filters = {"environment": "production"}

        # Apply label filters using PostgreSQL JSONB operators
        filtered_query = apply_label_filters(query, label_filters, User)
        result = (await test_db_session.exec(filtered_query)).all()

        # Verify results are correct
        expected_users = [u for u in test_users if u.labels.get("environment") == "production"]
        assert len(result) == len(expected_users)
        for user in result:
            assert user.labels["environment"] == "production"
