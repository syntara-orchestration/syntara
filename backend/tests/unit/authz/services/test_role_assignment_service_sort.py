"""Unit tests for _sort_value_from_row and _parse_sort in RoleAssignmentService module."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from syntara.authz.services.role_assignment_service import (
    RoleAssignmentService,
    _sort_value_from_row,
)
from syntara.core.utils.cursor import serialize_sort_value


def _make_row(
    *,
    project_id: str | None = None,
    role_name: str = "admin",
    principal_name: str = "alice",
    project_name: str | None = None,
    principal_type: str | None = "user",
) -> tuple[Any, ...]:
    """Build a mock result row matching the joined SELECT shape."""
    assignment = SimpleNamespace(project_id=project_id, role_name=role_name)
    return (assignment, principal_name, project_name, principal_type)


class TestSortValueFromRow:
    """Tests for _sort_value_from_row helper."""

    def test_created_at_returns_none(self) -> None:
        row = _make_row()
        assert _sort_value_from_row(row, "created_at") is None

    def test_principal_name(self) -> None:
        row = _make_row(principal_name="bob")
        assert _sort_value_from_row(row, "principal_name") == serialize_sort_value("bob")

    def test_project_name(self) -> None:
        row = _make_row(project_name="my-project")
        assert _sort_value_from_row(row, "project_name") == serialize_sort_value("my-project")

    def test_project_name_none(self) -> None:
        row = _make_row(project_name=None)
        assert _sort_value_from_row(row, "project_name") == serialize_sort_value(None)

    def test_principal_type(self) -> None:
        row = _make_row(principal_type="group")
        assert _sort_value_from_row(row, "principal_type") == serialize_sort_value("group")

    def test_principal_type_service_account(self) -> None:
        row = _make_row(principal_type="service_account")
        assert _sort_value_from_row(row, "principal_type") == serialize_sort_value("service_account")

    def test_principal_type_none(self) -> None:
        row = _make_row(principal_type=None)
        assert _sort_value_from_row(row, "principal_type") == serialize_sort_value(None)

    def test_scope_project(self) -> None:
        pid = str(uuid4())
        row = _make_row(project_id=pid)
        assert _sort_value_from_row(row, "scope") == serialize_sort_value("project")

    def test_scope_system(self) -> None:
        row = _make_row(project_id=None)
        assert _sort_value_from_row(row, "scope") == serialize_sort_value("system")

    def test_fallback_uses_getattr(self) -> None:
        row = _make_row(role_name="viewer")
        assert _sort_value_from_row(row, "role_name") == serialize_sort_value("viewer")


class TestParseSort:
    """Tests for RoleAssignmentService._parse_sort."""

    def test_none_returns_created_at_descending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort(None)
        assert field == "created_at"
        assert descending is True

    def test_empty_string_returns_created_at_descending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("")
        assert field == "created_at"
        assert descending is True

    def test_ascending_field(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("principal_name")
        assert field == "principal_name"
        assert descending is False

    def test_descending_field(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("-principal_name")
        assert field == "principal_name"
        assert descending is True

    def test_invalid_field_returns_created_at(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("nonexistent")
        assert field == "created_at"
        assert descending is True

    def test_principal_type_ascending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("principal_type")
        assert field == "principal_type"
        assert descending is False

    def test_principal_type_descending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("-principal_type")
        assert field == "principal_type"
        assert descending is True

    def test_scope_ascending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("scope")
        assert field == "scope"
        assert descending is False

    def test_scope_descending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("-scope")
        assert field == "scope"
        assert descending is True

    def test_role_name_ascending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("role_name")
        assert field == "role_name"
        assert descending is False

    def test_project_name_descending(self) -> None:
        field, descending = RoleAssignmentService._parse_sort("-project_name")
        assert field == "project_name"
        assert descending is True


class TestBuildCursors:
    """Tests for RoleAssignmentService._build_cursors."""

    def test_empty_rows_returns_null_cursors(self) -> None:
        result = RoleAssignmentService._build_cursors([], has_more=False, cursor=None, is_backward=False)
        assert result == {"next": None, "prev": None}

    def test_forward_with_more_returns_next(self) -> None:
        assignment = SimpleNamespace(id=uuid4(), created_at="2024-01-01T00:00:00Z", project_id=None)
        rows = [(assignment, "alice", None)]
        result = RoleAssignmentService._build_cursors(rows, has_more=True, cursor=None, is_backward=False)
        assert result["next"] is not None
        assert result["prev"] is None

    def test_forward_no_more_with_cursor_returns_prev(self) -> None:
        assignment = SimpleNamespace(id=uuid4(), created_at="2024-01-01T00:00:00Z", project_id=None)
        rows = [(assignment, "alice", None)]
        result = RoleAssignmentService._build_cursors(rows, has_more=False, cursor="some-cursor", is_backward=False)
        assert result["next"] is None
        assert result["prev"] is not None

    def test_forward_with_more_and_cursor_returns_both(self) -> None:
        a1 = SimpleNamespace(id=uuid4(), created_at="2024-01-01T00:00:00Z", project_id=None)
        a2 = SimpleNamespace(id=uuid4(), created_at="2024-01-02T00:00:00Z", project_id=None)
        rows = [(a1, "alice", None), (a2, "bob", None)]
        result = RoleAssignmentService._build_cursors(rows, has_more=True, cursor="some-cursor", is_backward=False)
        assert result["next"] is not None
        assert result["prev"] is not None

    def test_backward_with_cursor_returns_next(self) -> None:
        assignment = SimpleNamespace(id=uuid4(), created_at="2024-01-01T00:00:00Z", project_id=None)
        rows = [(assignment, "alice", None)]
        result = RoleAssignmentService._build_cursors(rows, has_more=False, cursor="some-cursor", is_backward=True)
        assert result["next"] is not None
        assert result["prev"] is None

    def test_backward_with_more_returns_prev(self) -> None:
        assignment = SimpleNamespace(id=uuid4(), created_at="2024-01-01T00:00:00Z", project_id=None)
        rows = [(assignment, "alice", None)]
        result = RoleAssignmentService._build_cursors(rows, has_more=True, cursor="some-cursor", is_backward=True)
        assert result["next"] is not None
        assert result["prev"] is not None

    def test_backward_with_more_and_cursor_returns_both(self) -> None:
        a1 = SimpleNamespace(id=uuid4(), created_at="2024-01-01T00:00:00Z", project_id=None)
        a2 = SimpleNamespace(id=uuid4(), created_at="2024-01-02T00:00:00Z", project_id=None)
        rows = [(a1, "alice", None), (a2, "bob", None)]
        result = RoleAssignmentService._build_cursors(rows, has_more=True, cursor="some-cursor", is_backward=True)
        assert result["next"] is not None
        assert result["prev"] is not None


class TestResolveSortCol:
    """Tests for RoleAssignmentService._resolve_sort_col."""

    def test_principal_name_returns_given_col(self) -> None:
        sentinel = object()
        result = RoleAssignmentService._resolve_sort_col("principal_name", sentinel, None, None)
        assert result is sentinel

    def test_project_name_returns_project_model_col(self) -> None:
        from syntara.authz.models import Project

        result = RoleAssignmentService._resolve_sort_col("project_name", None, None, None)
        assert result is Project.name

    def test_principal_type_returns_given_col(self) -> None:
        sentinel = object()
        result = RoleAssignmentService._resolve_sort_col("principal_type", None, None, sentinel)
        assert result is sentinel

    def test_scope_returns_scope_col(self) -> None:
        sentinel = object()
        result = RoleAssignmentService._resolve_sort_col("scope", None, sentinel, None)
        assert result is sentinel

    def test_fallback_returns_model_attribute(self) -> None:
        from syntara.authz.models import RoleAssignment

        result = RoleAssignmentService._resolve_sort_col("created_at", None, None, None)
        assert result is RoleAssignment.created_at


class TestBuildSortExpr:
    """Tests for RoleAssignmentService._build_sort_expr."""

    def test_asc_forward(self) -> None:
        from sqlalchemy import Column, String

        col = Column("test", String)
        expr = RoleAssignmentService._build_sort_expr(col, effective_desc=False, is_backward=False)
        compiled = str(expr.compile())
        assert "ASC" in compiled
        assert "NULLS LAST" in compiled

    def test_asc_backward(self) -> None:
        from sqlalchemy import Column, String

        col = Column("test", String)
        expr = RoleAssignmentService._build_sort_expr(col, effective_desc=False, is_backward=True)
        compiled = str(expr.compile())
        assert "ASC" in compiled
        assert "NULLS FIRST" in compiled

    def test_desc_forward(self) -> None:
        from sqlalchemy import Column, String

        col = Column("test", String)
        expr = RoleAssignmentService._build_sort_expr(col, effective_desc=True, is_backward=False)
        compiled = str(expr.compile())
        assert "DESC" in compiled
        assert "NULLS LAST" in compiled

    def test_desc_backward(self) -> None:
        from sqlalchemy import Column, String

        col = Column("test", String)
        expr = RoleAssignmentService._build_sort_expr(col, effective_desc=True, is_backward=True)
        compiled = str(expr.compile())
        assert "DESC" in compiled
        assert "NULLS FIRST" in compiled
