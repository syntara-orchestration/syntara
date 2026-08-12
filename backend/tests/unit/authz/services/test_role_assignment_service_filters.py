"""Unit tests for _apply_attribute_filters and _apply_visibility_filter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from syntara.authz.services.role_assignment_service import RoleAssignmentService


def _make_base() -> MagicMock:
    """Create a mock query object that supports chained .where() calls."""
    base = MagicMock()
    base.where.return_value = base
    return base


def _make_col() -> MagicMock:
    """Create a mock column with comparison and ilike support."""
    col = MagicMock()
    col.ilike = MagicMock(return_value="ilike_clause")
    return col


def _defaults(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return default kwargs for _apply_attribute_filters with all None/empty."""
    defaults = {
        "principal_id": None,
        "group_id": None,
        "principal_name": None,
        "principal_name_col": MagicMock(),
        "principal_name_contains": None,
        "role_name": None,
        "role_name_contains": None,
        "project_id": None,
        "principal_type": None,
        "principal_type_col": MagicMock(),
        "scope": None,
    }
    defaults.update(overrides)
    return defaults


class TestApplyAttributeFiltersNoFilters:
    """When all filter values are None, no .where() calls are made."""

    def test_returns_base_unchanged(self) -> None:
        base = _make_base()
        result = RoleAssignmentService._apply_attribute_filters(base, **_defaults())
        assert result is base
        base.where.assert_not_called()


class TestApplyAttributeFiltersPrincipalId:
    """Tests for principal_id filter."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        pid = uuid4()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(principal_id=pid))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersGroupId:
    """Tests for group_id filter."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        gid = uuid4()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(group_id=gid))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersPrincipalName:
    """Tests for principal_name exact-match filter."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        col = _make_col()
        RoleAssignmentService._apply_attribute_filters(
            base, **_defaults(principal_name="alice", principal_name_col=col)
        )
        assert base.where.call_count == 1


class TestApplyAttributeFiltersPrincipalNameContains:
    """Tests for principal_name_contains partial match."""

    def test_applies_ilike_where(self) -> None:
        base = _make_base()
        col = _make_col()
        RoleAssignmentService._apply_attribute_filters(
            base, **_defaults(principal_name_contains="ali", principal_name_col=col)
        )
        col.ilike.assert_called_once_with("%ali%")
        assert base.where.call_count == 1


class TestApplyAttributeFiltersRoleName:
    """Tests for role_name exact-match filter."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(role_name="admin"))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersRoleNameContains:
    """Tests for role_name_contains partial match."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(role_name_contains="adm"))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersProjectId:
    """Tests for project_id filter."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        pid = uuid4()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(project_id=pid))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersPrincipalType:
    """Tests for principal_type filter."""

    def test_applies_where_clause(self) -> None:
        base = _make_base()
        col = _make_col()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(principal_type="user", principal_type_col=col))
        assert base.where.call_count == 1

    def test_group_type(self) -> None:
        base = _make_base()
        col = _make_col()
        RoleAssignmentService._apply_attribute_filters(
            base, **_defaults(principal_type="group", principal_type_col=col)
        )
        assert base.where.call_count == 1

    def test_service_account_type(self) -> None:
        base = _make_base()
        col = _make_col()
        RoleAssignmentService._apply_attribute_filters(
            base, **_defaults(principal_type="service_account", principal_type_col=col)
        )
        assert base.where.call_count == 1


class TestApplyAttributeFiltersScopeSystem:
    """Tests for scope='system' filter."""

    def test_applies_is_none_clause(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(scope="system"))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersScopeProject:
    """Tests for scope='project' filter."""

    def test_applies_is_not_none_clause(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(scope="project"))
        assert base.where.call_count == 1


class TestApplyAttributeFiltersScopeInvalid:
    """Tests that an unrecognized scope value does not add a clause."""

    def test_unknown_scope_no_clause(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_attribute_filters(base, **_defaults(scope="global"))
        base.where.assert_not_called()


class TestApplyAttributeFiltersMultiple:
    """Tests for combining multiple filters."""

    def test_all_filters_applied(self) -> None:
        base = _make_base()
        pid = uuid4()
        gid = uuid4()
        proj = uuid4()
        col = _make_col()
        pt_col = _make_col()
        RoleAssignmentService._apply_attribute_filters(
            base,
            principal_id=pid,
            group_id=gid,
            principal_name="alice",
            principal_name_col=col,
            principal_name_contains="ali",
            role_name="admin",
            role_name_contains="adm",
            project_id=proj,
            principal_type="user",
            principal_type_col=pt_col,
            scope="system",
        )
        assert base.where.call_count == 9


# ---------------------------------------------------------------------------
# _apply_visibility_filter
# ---------------------------------------------------------------------------


class TestApplyVisibilityFilterNone:
    """When all visibility params are None, base is returned unchanged."""

    def test_returns_base_unchanged(self) -> None:
        base = _make_base()
        result = RoleAssignmentService._apply_visibility_filter(
            base, restrict_user_id=None, restrict_group_ids=None, allowed_project_ids=None
        )
        assert result is base
        base.where.assert_not_called()


class TestApplyVisibilityFilterUser:
    """restrict_user_id adds a principal_id clause."""

    def test_applies_user_clause(self) -> None:
        base = _make_base()
        uid = uuid4()
        RoleAssignmentService._apply_visibility_filter(
            base, restrict_user_id=uid, restrict_group_ids=None, allowed_project_ids=None
        )
        assert base.where.call_count == 1


class TestApplyVisibilityFilterGroups:
    """restrict_group_ids adds a group_id IN clause."""

    def test_applies_group_clause(self) -> None:
        base = _make_base()
        gids = [uuid4(), uuid4()]
        RoleAssignmentService._apply_visibility_filter(
            base, restrict_user_id=None, restrict_group_ids=gids, allowed_project_ids=None
        )
        assert base.where.call_count == 1


class TestApplyVisibilityFilterProjects:
    """allowed_project_ids adds a project_id IN clause."""

    def test_applies_project_clause(self) -> None:
        base = _make_base()
        pids = [uuid4()]
        RoleAssignmentService._apply_visibility_filter(
            base, restrict_user_id=None, restrict_group_ids=None, allowed_project_ids=pids
        )
        assert base.where.call_count == 1


class TestApplyVisibilityFilterCombined:
    """Multiple visibility params combine via OR."""

    def test_all_three_applied(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_visibility_filter(
            base,
            restrict_user_id=uuid4(),
            restrict_group_ids=[uuid4()],
            allowed_project_ids=[uuid4()],
        )
        assert base.where.call_count == 1


class TestApplyVisibilityFilterEmptyLists:
    """Empty lists (truthy check fails) still trigger the outer branch."""

    def test_empty_groups_no_clause(self) -> None:
        base = _make_base()
        RoleAssignmentService._apply_visibility_filter(
            base, restrict_user_id=None, restrict_group_ids=[], allowed_project_ids=None
        )
        base.where.assert_called_once()
