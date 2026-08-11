"""Unit tests for BaseService._apply_access_filters."""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import String, TypeDecorator, column
from sqlmodel import select

from syntara.authz.engine import AllowedProjectsResult
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.services.base import BaseService
from syntara.core.utils.cursor import (
    PaginationDirection,
    SortDirection,
    create_cursor_data,
    encode_cursor,
    serialize_sort_value,
)
from syntara.workflows.models.workflow import Workflow


class TestApplyAccessFilters:
    """Tests for BaseService._apply_access_filters static method."""

    def test_no_filters_returns_query(self) -> None:
        query = select(User)
        result = BaseService._apply_access_filters(query, User, None, None)
        assert result is not None

    def test_all_projects_returns_query(self) -> None:
        query = select(Workflow)
        allowed = AllowedProjectsResult(all_projects=True, project_ids=[])
        result = BaseService._apply_access_filters(query, Workflow, allowed, None)
        assert result is not None

    def test_empty_project_ids_returns_none(self) -> None:
        query = select(Workflow)
        allowed = AllowedProjectsResult(all_projects=False, project_ids=[])
        result = BaseService._apply_access_filters(query, Workflow, allowed, None)
        assert result is None

    def test_project_ids_returns_filtered_query(self) -> None:
        query = select(Workflow)
        pid = uuid4()
        allowed = AllowedProjectsResult(all_projects=False, project_ids=[pid])
        result = BaseService._apply_access_filters(query, Workflow, allowed, None)
        assert result is not None

    def test_model_without_project_id_raises(self) -> None:
        query = select(User)
        allowed = AllowedProjectsResult(all_projects=False, project_ids=[uuid4()])
        with pytest.raises(ValueError, match="does not have a project_id field"):
            BaseService._apply_access_filters(query, User, allowed, None)

    def test_empty_id_restriction_returns_none(self) -> None:
        query = select(User)
        result = BaseService._apply_access_filters(query, User, None, [])
        assert result is None

    def test_id_restriction_returns_filtered_query(self) -> None:
        query = select(User)
        result = BaseService._apply_access_filters(query, User, None, [uuid4()])
        assert result is not None

    def test_both_filters_applied(self) -> None:
        query = select(Workflow)
        pid = uuid4()
        uid = uuid4()
        allowed = AllowedProjectsResult(all_projects=False, project_ids=[pid])
        result = BaseService._apply_access_filters(query, Workflow, allowed, [uid])
        assert result is not None

    def test_project_allowed_but_empty_id_restriction(self) -> None:
        query = select(Workflow)
        pid = uuid4()
        allowed = AllowedProjectsResult(all_projects=False, project_ids=[pid])
        result = BaseService._apply_access_filters(query, Workflow, allowed, [])
        assert result is None


class TestApplyCursorPagination:
    """Tests for BaseService._apply_cursor_pagination keyset coercion."""

    def test_deserializes_datetime_sort_value_for_updated_at(self) -> None:
        """Regression: ISO sort_value must be coerced before comparing to updated_at."""
        service = object.__new__(BaseService)
        boundary = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        cursor = encode_cursor(
            create_cursor_data(
                resource_id=uuid4(),
                created_at=boundary,
                direction=PaginationDirection.NEXT,
                sort_field="updated_at",
                sort_direction=SortDirection.DESC,
                sort_value=serialize_sort_value(boundary),
            )
        )

        query, needs_reverse = service._apply_cursor_pagination(
            select(Workflow),
            cursor,
            "updated_at",
            SortDirection.DESC,
            Workflow,
        )

        assert needs_reverse is False
        # Compiled SQL should bind a datetime, not the ISO string from the cursor.
        compiled = query.compile(compile_kwargs={"literal_binds": True})
        assert boundary.isoformat() in str(compiled) or "2025-01-15" in str(compiled)

    def test_malformed_datetime_sort_value_raises_safe_value_error(self) -> None:
        """Malformed sort_value must surface as SafeValueError (422), not HTTP 500."""
        service = object.__new__(BaseService)
        cursor = encode_cursor(
            create_cursor_data(
                resource_id=uuid4(),
                created_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
                direction=PaginationDirection.NEXT,
                sort_field="updated_at",
                sort_direction=SortDirection.DESC,
                sort_value="not-a-datetime",
            )
        )

        query = select(Workflow)
        with pytest.raises(SafeValueError, match="Invalid cursor format"):
            service._apply_cursor_pagination(
                query,
                cursor,
                "updated_at",
                SortDirection.DESC,
                Workflow,
            )

    def test_boolean_sort_value_keyset_does_not_raise(self) -> None:
        """Boolean sorts must cast for < / > — SQLAlchemy forbids bool inequalities."""
        service = object.__new__(BaseService)
        cursor = encode_cursor(
            create_cursor_data(
                resource_id=uuid4(),
                created_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
                direction=PaginationDirection.NEXT,
                sort_field="is_enabled",
                sort_direction=SortDirection.ASC,
                sort_value="false",
            )
        )

        query, needs_reverse = service._apply_cursor_pagination(
            select(Workflow),
            cursor,
            "is_enabled",
            SortDirection.ASC,
            Workflow,
        )

        assert needs_reverse is False
        # Compiling would raise ArgumentError before the int cast fix.
        _ = query.compile()

    def test_boolean_prev_keyset_sets_needs_reverse(self) -> None:
        service = object.__new__(BaseService)
        cursor = encode_cursor(
            create_cursor_data(
                resource_id=uuid4(),
                created_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
                direction=PaginationDirection.PREV,
                sort_field="is_enabled",
                sort_direction=SortDirection.ASC,
                sort_value="false",
            )
        )

        query, needs_reverse = service._apply_cursor_pagination(
            select(Workflow),
            cursor,
            "is_enabled",
            SortDirection.ASC,
            Workflow,
        )

        assert needs_reverse is True
        _ = query.compile()

    def test_invalid_cursor_id_ignores_keyset_filter(self) -> None:
        service = object.__new__(BaseService)
        cursor = encode_cursor(
            create_cursor_data(
                resource_id="not-a-uuid",
                created_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
                direction=PaginationDirection.NEXT,
                sort_field="name",
                sort_direction=SortDirection.ASC,
                sort_value="alice",
            )
        )
        query = select(Workflow)

        result_query, needs_reverse = service._apply_cursor_pagination(
            query,
            cursor,
            "name",
            SortDirection.ASC,
            Workflow,
        )

        assert needs_reverse is False
        assert result_query is query

    def test_invalid_created_at_ignores_keyset_filter(self) -> None:
        service = object.__new__(BaseService)
        cursor = encode_cursor(
            {
                "id": str(uuid4()),
                "created_at": "not-a-datetime",
                "direction": "next",
            }
        )
        query = select(Workflow)

        result_query, needs_reverse = service._apply_cursor_pagination(
            query,
            cursor,
            "created_at",
            SortDirection.DESC,
            Workflow,
        )

        assert needs_reverse is False
        assert result_query is query

    def test_missing_python_type_falls_back_to_string_compare(self) -> None:
        service = object.__new__(BaseService)
        boundary = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        cursor = encode_cursor(
            create_cursor_data(
                resource_id=uuid4(),
                created_at=boundary,
                direction=PaginationDirection.NEXT,
                sort_field="name",
                sort_direction=SortDirection.ASC,
                sort_value="alice",
            )
        )

        class _NoPythonType(TypeDecorator[str]):
            impl = String
            cache_ok = True

            @property
            def python_type(self) -> type:
                raise NotImplementedError

        fake_col = column("name", _NoPythonType())
        with patch.object(Workflow, "name", fake_col, create=True):
            query, needs_reverse = service._apply_cursor_pagination(
                select(Workflow),
                cursor,
                "name",
                SortDirection.ASC,
                Workflow,
            )

        assert needs_reverse is False
        _ = query.compile()

    def test_coerce_boolean_keyset_leaves_non_bool_unchanged(self) -> None:
        col = Workflow.name
        out_col, out_val = BaseService._coerce_boolean_keyset(col, "alice")
        assert out_col is col
        assert out_val == "alice"

    def test_coerce_boolean_keyset_casts_bool(self) -> None:
        col = Workflow.is_enabled
        out_col, out_val = BaseService._coerce_boolean_keyset(col, val=True)
        assert out_val == 1
        assert out_col is not col

    def test_coerce_boolean_keyset_casts_false(self) -> None:
        col = Workflow.is_enabled
        out_col, out_val = BaseService._coerce_boolean_keyset(col, val=False)
        assert out_val == 0
        assert out_col is not col
