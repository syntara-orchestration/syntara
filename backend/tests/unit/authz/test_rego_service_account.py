"""Rego policy tests for service_account resource type."""

from typing import Any

import pytest

from syntara.authz.role_conventions import BUILTIN_POLICIES
from tests.unit.authz.conftest import allow_policy, build_opa_input, policies_for_role

SA_ACTIONS = sorted({p.action for p in BUILTIN_POLICIES if p.resource == "service_account"})
assert {"create", "read", "update", "delete", "rotate_secret", "disable", "enable"} <= set(SA_ACTIONS)
SA_WRITE_ACTIONS = sorted(set(SA_ACTIONS) - {"read"})

PROJECT_ID = "proj-sa-test"
OTHER_PROJECT_ID = "proj-other"


def _project_admin_policies(project: str = PROJECT_ID) -> list[dict[str, Any]]:
    return [
        allow_policy(
            f"service_account:{action}:{project}",
            [f"service_account:{action}"],
            scope="project",
            project=project,
        )
        for action in SA_ACTIONS
    ]


def _system_admin_policies() -> list[dict[str, Any]]:
    """Build admin role policies (all scope='any', no project injection needed)."""
    return policies_for_role("admin")


def _auditor_policies(project: str = PROJECT_ID) -> list[dict[str, Any]]:
    return [
        allow_policy(
            f"service_account:read:{project}",
            ["service_account:read"],
            scope="project",
            project=project,
        ),
    ]


class TestProjectAdminServiceAccountAccess:
    """Project-admin has full service_account access in their project."""

    @pytest.mark.parametrize("action", SA_ACTIONS, ids=SA_ACTIONS)
    def test_allowed_in_own_project(self, opa_evaluate, action: str):
        result = opa_evaluate(
            build_opa_input(
                action=action,
                resource_type="service_account",
                resource_project=PROJECT_ID,
                effective_policies=_project_admin_policies(),
            )
        )
        assert result["allow"] is True

    @pytest.mark.parametrize("action", SA_ACTIONS, ids=SA_ACTIONS)
    def test_denied_in_other_project(self, opa_evaluate, action: str):
        result = opa_evaluate(
            build_opa_input(
                action=action,
                resource_type="service_account",
                resource_project=OTHER_PROJECT_ID,
                effective_policies=_project_admin_policies(),
            )
        )
        assert result["allow"] is False


class TestSystemAdminServiceAccountAccess:
    """System admin role has full service_account access in any project."""

    @pytest.mark.parametrize("action", SA_ACTIONS, ids=SA_ACTIONS)
    def test_allowed_in_project(self, opa_evaluate, action: str):
        result = opa_evaluate(
            build_opa_input(
                action=action,
                resource_type="service_account",
                resource_project=PROJECT_ID,
                effective_policies=_system_admin_policies(),
            )
        )
        assert result["allow"] is True

    @pytest.mark.parametrize("action", SA_ACTIONS, ids=SA_ACTIONS)
    def test_allowed_in_any_project(self, opa_evaluate, action: str):
        result = opa_evaluate(
            build_opa_input(
                action=action,
                resource_type="service_account",
                resource_project=OTHER_PROJECT_ID,
                effective_policies=_system_admin_policies(),
            )
        )
        assert result["allow"] is True


class TestProjectAuditorServiceAccountAccess:
    """Project-auditor can only read service_accounts."""

    def test_read_allowed(self, opa_evaluate):
        result = opa_evaluate(
            build_opa_input(
                action="read",
                resource_type="service_account",
                resource_project=PROJECT_ID,
                effective_policies=_auditor_policies(),
            )
        )
        assert result["allow"] is True

    @pytest.mark.parametrize("action", SA_WRITE_ACTIONS, ids=SA_WRITE_ACTIONS)
    def test_write_actions_denied(self, opa_evaluate, action: str):
        result = opa_evaluate(
            build_opa_input(
                action=action,
                resource_type="service_account",
                resource_project=PROJECT_ID,
                effective_policies=_auditor_policies(),
            )
        )
        assert result["allow"] is False


class TestNoPoliciesServiceAccountAccess:
    """Without any policies, all service_account actions are denied."""

    @pytest.mark.parametrize("action", SA_ACTIONS, ids=SA_ACTIONS)
    def test_all_actions_denied(self, opa_evaluate, action: str):
        result = opa_evaluate(
            build_opa_input(
                action=action,
                resource_type="service_account",
                resource_project=PROJECT_ID,
                effective_policies=[],
            )
        )
        assert result["allow"] is False
