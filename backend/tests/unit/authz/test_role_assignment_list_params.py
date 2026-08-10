"""Unit tests for RoleAssignmentListParams schema validation."""

import pytest
from pydantic import ValidationError

from syntara.authz.role_assignment_router import RoleAssignmentListParams


class TestPrincipalTypeParam:
    """Validate the principal_type query parameter accepts only valid literals."""

    def test_accepts_user(self) -> None:
        params = RoleAssignmentListParams(principal_type="user")
        assert params.principal_type == "user"

    def test_accepts_group(self) -> None:
        params = RoleAssignmentListParams(principal_type="group")
        assert params.principal_type == "group"

    def test_accepts_service_account(self) -> None:
        params = RoleAssignmentListParams(principal_type="service_account")
        assert params.principal_type == "service_account"

    def test_accepts_none(self) -> None:
        params = RoleAssignmentListParams(principal_type=None)
        assert params.principal_type is None

    def test_defaults_to_none(self) -> None:
        params = RoleAssignmentListParams()
        assert params.principal_type is None

    def test_rejects_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            RoleAssignmentListParams(principal_type="robot")


class TestScopeParam:
    """Validate the scope query parameter accepts only valid literals."""

    def test_accepts_system(self) -> None:
        params = RoleAssignmentListParams(scope="system")
        assert params.scope == "system"

    def test_accepts_project(self) -> None:
        params = RoleAssignmentListParams(scope="project")
        assert params.scope == "project"

    def test_accepts_none(self) -> None:
        params = RoleAssignmentListParams(scope=None)
        assert params.scope is None

    def test_defaults_to_none(self) -> None:
        params = RoleAssignmentListParams()
        assert params.scope is None

    def test_rejects_invalid_value(self) -> None:
        with pytest.raises(ValidationError):
            RoleAssignmentListParams(scope="global")
