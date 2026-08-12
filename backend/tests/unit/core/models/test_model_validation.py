"""Unit tests for SQLModel validation rules.

This module tests the validation behavior of all SQLModel classes
to ensure proper data validation and error handling.

Note: Due to SQLModel/SQLAlchemy compatibility issues with multiple inheritance
and JSON columns, these tests focus on validation logic using Error and
pagination models that are working correctly.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import (
    ResourcesResponse,
    ResourcesResponseBase,
)

# Note: SQLModel base class tests are temporarily disabled due to
# SQLModel/SQLAlchemy compatibility issues with JSON columns and multiple inheritance.
# These will be re-enabled once the underlying SQLModel compatibility issues are resolved.


class TestPaginationValidation:
    """Test validation rules for pagination models."""

    def test_valid_resources_response_base(self) -> None:
        """Test creation of valid ResourcesResponseBase."""
        response = ResourcesResponseBase(next="eyJpZCI6InV1aWQifQ==", prev=None, total=100)

        assert response.next == "eyJpZCI6InV1aWQifQ=="
        assert response.prev is None
        assert response.total == 100

    def test_resources_response_base_negative_total(self) -> None:
        """Test ResourcesResponseBase with negative total."""
        with pytest.raises(ValidationError):
            ResourcesResponseBase(
                next=None,
                prev=None,
                total=-1,  # Must be >= 0
            )

    def test_valid_resources_response(self) -> None:
        """Test creation of valid ResourcesResponse."""
        # Create some mock resources
        resources = [{"id": str(uuid4()), "name": "Resource 1"}, {"id": str(uuid4()), "name": "Resource 2"}]

        response = ResourcesResponse[dict[str, str]](
            resources=resources, next="eyJpZCI6InV1aWQifQ==", prev=None, total=100
        )

        assert len(response.resources) == 2
        assert response.resources[0]["name"] == "Resource 1"

    def test_resources_response_many_items(self) -> None:
        """Test ResourcesResponse rejects lists exceeding max page size."""
        resources = [{"id": str(uuid4())} for _ in range(101)]

        with pytest.raises(ValidationError, match="too_long"):
            ResourcesResponse[dict[str, str]](
                resources=resources,
                next=None,
                prev=None,
            )


class TestBaseListParamsValidation:
    """Test validation rules for BaseListParams query parameters."""

    @pytest.mark.parametrize(
        ("value", "valid"),
        [
            ("name", True),
            ("-name", True),
            ("-created_at", True),
            ("a", True),
            ("z9_field", True),
            ("", False),
            ("-", False),
            ("Name", False),
            ("_name", False),
            ("123", False),
            ("-Capital", False),
            ("field name", False),
            ("field.name", False),
            ("name,-created_at", False),
            ("name; DROP TABLE", False),
            ("name--", False),
        ],
    )
    def test_sort_pattern(self, value: str, *, valid: bool) -> None:
        """Test sort parameter regex accepts valid field names and rejects invalid ones."""
        if valid:
            params = BaseListParams(sort=value)
            assert params.sort == value
        else:
            with pytest.raises(ValidationError):
                BaseListParams(sort=value)

    def test_sort_none_is_valid(self) -> None:
        """Test sort parameter accepts None (optional)."""
        params = BaseListParams(sort=None)
        assert params.sort is None

    def test_sort_default_is_none(self) -> None:
        """Test sort parameter defaults to None."""
        params = BaseListParams()
        assert params.sort is None
