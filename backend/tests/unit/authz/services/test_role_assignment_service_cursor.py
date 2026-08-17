"""Unit tests for _sort_col_where_clause and _apply_cursor in RoleAssignmentService."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from syntara.authz.services.role_assignment_service import RoleAssignmentService
from syntara.core.utils.cursor import CursorData, encode_cursor

metadata = sa.MetaData()
_test_table = sa.Table(
    "t",
    metadata,
    sa.Column("sort_val", sa.String),
    sa.Column("created_at", sa.DateTime),
    sa.Column("id", sa.String),
)
_sort_col = _test_table.c.sort_val
_created_at_col = _test_table.c.created_at
_id_col = _test_table.c.id

_CURSOR_DT = datetime(2024, 1, 1, tzinfo=UTC)
_CURSOR_ID = "rid-1"
_CURSOR_SV = "alpha"
_NULL_SV = ""

_BASE_STMT = sa.select(_test_table)


def _compile(clause: sa.ClauseElement) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def _make_cursor(
    *,
    rid: str = _CURSOR_ID,
    cat: str = "2024-01-01T00:00:00+00:00",
    direction: str = "next",
    sort_field: str | None = None,
    sort_value: str | None = None,
) -> str:
    data: CursorData = {"id": rid, "created_at": cat, "direction": direction}
    if sort_field is not None:
        data["sort_field"] = sort_field
    if sort_value is not None:
        data["sort_value"] = sort_value
    return encode_cursor(data)


class TestSortColWhereClauseNullCursor:
    """NULL cursor (cursor_sv == '') paths."""

    def test_forward_asc_returns_only_nulls(self) -> None:
        """ASC forward from NULL cursor: only NULL rows with later tiebreaker."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _NULL_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=False,
            is_backward=False,
        )
        sql = _compile(result)
        assert "IS NULL" in sql
        assert "IS NOT NULL" not in sql
        assert ">" in sql

    def test_forward_desc_returns_only_nulls(self) -> None:
        """DESC forward from NULL cursor: only NULL rows with earlier tiebreaker."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _NULL_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=True,
            is_backward=False,
        )
        sql = _compile(result)
        assert "IS NULL" in sql
        assert "IS NOT NULL" not in sql
        assert "<" in sql

    def test_backward_asc_includes_non_nulls(self) -> None:
        """ASC backward from NULL: must include non-NULL rows to cross boundary."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _NULL_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=True,
            is_backward=True,
        )
        sql = _compile(result)
        assert "IS NULL" in sql
        assert "IS NOT NULL" in sql

    def test_backward_desc_includes_non_nulls(self) -> None:
        """DESC backward from NULL: must include non-NULL rows to cross boundary."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _NULL_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=False,
            is_backward=True,
        )
        sql = _compile(result)
        assert "IS NULL" in sql
        assert "IS NOT NULL" in sql


class TestSortColWhereClauseNonNullCursor:
    """Non-NULL cursor (cursor_sv != '') paths."""

    def test_forward_asc_includes_nulls(self) -> None:
        """ASC forward: include NULL rows (they come after non-NULLs in NULLS LAST)."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _CURSOR_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=False,
            is_backward=False,
        )
        sql = _compile(result)
        assert "IS NULL" in sql
        assert ">" in sql

    def test_forward_desc_includes_nulls(self) -> None:
        """DESC forward: include NULL rows (they come after non-NULLs in NULLS LAST)."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _CURSOR_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=True,
            is_backward=False,
        )
        sql = _compile(result)
        assert "IS NULL" in sql
        assert "<" in sql

    def test_backward_asc_excludes_nulls(self) -> None:
        """ASC backward from non-NULL: NULLs are after, not before."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _CURSOR_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=True,
            is_backward=True,
        )
        sql = _compile(result)
        assert "IS NULL" not in sql
        assert "<" in sql

    def test_backward_desc_excludes_nulls(self) -> None:
        """DESC backward from non-NULL: NULLs are after, not before."""
        result = RoleAssignmentService._sort_col_where_clause(
            _sort_col,
            _created_at_col,
            _id_col,
            _CURSOR_SV,
            _CURSOR_DT,
            _CURSOR_ID,
            go_forward=False,
            is_backward=True,
        )
        sql = _compile(result)
        assert "IS NULL" not in sql
        assert ">" in sql


class TestApplyCursorNoCursor:
    """_apply_cursor with no cursor returns stmt unchanged."""

    def test_none_cursor_returns_unchanged(self) -> None:
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, None, _sort_col, _created_at_col, _id_col, descending=False
        )
        assert _compile(stmt) == _compile(_BASE_STMT)
        assert is_backward is False

    def test_empty_cursor_returns_unchanged(self) -> None:
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, "", _sort_col, _created_at_col, _id_col, descending=False
        )
        assert _compile(stmt) == _compile(_BASE_STMT)
        assert is_backward is False


class TestApplyCursorWithoutSortCol:
    """_apply_cursor when use_sort_col is False (sort_field == created_at or no sort_value)."""

    def test_forward_asc_adds_where_clause(self) -> None:
        cursor = _make_cursor(direction="next")
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=False, sort_field="created_at"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert is_backward is False

    def test_forward_desc_adds_lt_clause(self) -> None:
        cursor = _make_cursor(direction="next")
        stmt, _ = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=True, sort_field="created_at"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert "<" in sql

    def test_backward_asc_uses_go_forward_path(self) -> None:
        """ASC backward: go_forward = descending ^ is_backward = False ^ True = True, so < clause."""
        cursor = _make_cursor(direction="prev")
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=False, sort_field="created_at"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert "<" in sql
        assert is_backward is True

    def test_backward_desc_uses_not_go_forward_path(self) -> None:
        """DESC backward: go_forward = True ^ True = False, so > clause."""
        cursor = _make_cursor(direction="prev")
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=True, sort_field="created_at"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert ">" in sql
        assert is_backward is True


class TestApplyCursorWithSortCol:
    """_apply_cursor when use_sort_col is True (cursor has sort_value matching sort_field)."""

    def test_delegates_to_sort_col_where_clause(self) -> None:
        cursor = _make_cursor(sort_field="principal_name", sort_value="alice")
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=False, sort_field="principal_name"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert is_backward is False

    def test_backward_with_sort_col(self) -> None:
        cursor = _make_cursor(direction="prev", sort_field="principal_name", sort_value="alice")
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=False, sort_field="principal_name"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert is_backward is True

    def test_null_sort_value_uses_sort_col(self) -> None:
        cursor = _make_cursor(sort_field="principal_name", sort_value="")
        stmt, _ = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=False, sort_field="principal_name"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert "IS NULL" in sql

    def test_mismatched_sort_field_falls_back(self) -> None:
        cursor = _make_cursor(sort_field="role_name", sort_value="admin")
        stmt, _ = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=False, sort_field="principal_name"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert "IS NULL" not in sql

    def test_desc_forward_with_sort_col(self) -> None:
        cursor = _make_cursor(sort_field="principal_name", sort_value="alice")
        stmt, _ = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=True, sort_field="principal_name"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql

    def test_desc_backward_with_sort_col(self) -> None:
        cursor = _make_cursor(direction="prev", sort_field="principal_name", sort_value="alice")
        stmt, is_backward = RoleAssignmentService._apply_cursor(
            _BASE_STMT, cursor, _sort_col, _created_at_col, _id_col, descending=True, sort_field="principal_name"
        )
        sql = _compile(stmt)
        assert "WHERE" in sql
        assert is_backward is True
