"""Policy coverage: system-scoped (any) policies — representative subset.

Unit tests in tests/unit/authz/ exhaustively cover all 53 system-scoped
policies through Rego/Rego evaluation. These e2e tests verify a
representative sample (~13 policies) through the full HTTP stack.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import ProjectFactory, RoleFactory, UserFactory, UserRoleAssignmentFactory
    from syntara_api_client.api import SyntaraApiRegistry

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for

from .conftest import SELF_SCOPED_CASES, SYSTEM_SCOPED_REPRESENTATIVE

pytestmark = [pytest.mark.e2e]


@pytest.mark.parametrize("case", SYSTEM_SCOPED_REPRESENTATIVE, ids=lambda c: c.policy)
class TestSystemScopedPolicyAllowed:
    """Positive: user WITH the system policy can perform the action."""

    def test_allowed(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_role: RoleFactory,
        create_user: UserFactory,
        assign_system_role: UserRoleAssignmentFactory,
        case,
    ) -> None:
        user_id, username, password = create_user(admin_api, "sys-a")
        project_id, _ = create_project(admin_api, "sys-a")

        all_policies = [case.policy, *case.prereqs]
        role_name = create_role(admin_api, "sys", all_policies)
        assign_system_role(admin_api, user_id, role_name)

        ctx: dict[str, Any] = {}
        if case.setup:
            case.setup(admin_api, project_id, ctx)

        user_api = api_for(syntara_base_url, username, password)
        resp = case.action(user_api, project_id, ctx)
        assert resp.is_success


@pytest.mark.parametrize("case", SYSTEM_SCOPED_REPRESENTATIVE, ids=lambda c: c.policy)
class TestSystemScopedPolicyDenied:
    """Negative: user WITHOUT the system policy is denied."""

    def test_denied(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_user: UserFactory,
        create_project: ProjectFactory,
        create_role: RoleFactory,
        assign_system_role: UserRoleAssignmentFactory,
        case,
    ) -> None:
        if case.skip_denied:
            pytest.skip("List endpoint returns built-in items to all authenticated users")

        user_id, username, password = create_user(admin_api, "sys-d")
        project_id, _ = create_project(admin_api, "sys-d")

        if case.prereqs:
            role_name = create_role(admin_api, "sysnp", case.prereqs)
            assign_system_role(admin_api, user_id, role_name)

        ctx: dict[str, Any] = {}
        if case.setup:
            case.setup(admin_api, project_id, ctx)

        user_api = api_for(syntara_base_url, username, password)
        resp = case.action(user_api, project_id, ctx)

        if resp.status_code == HTTPStatus.FORBIDDEN:
            return
        if resp.is_success and resp.parsed is not None and hasattr(resp.parsed, "resources"):
            resource_ids = {str(getattr(r, "id", None)) for r in resp.parsed.resources}
            assert str(project_id) not in resource_ids, (
                f"Expected {case.policy} to be denied, but test-created project "
                f"{project_id} is visible among {len(resp.parsed.resources)} resources"
            )
            return
        assert resp.status_code == HTTPStatus.FORBIDDEN, f"Expected denied, got {resp.status_code}: {resp.content!r}"


class TestSelfScopedPoliciesCoverage:
    """Self-scoped policies are tested in test_baseline.py.

    This class documents coverage status for the 5 self-scoped policies.
    """

    def test_coverage_note(self) -> None:
        """Verify all 5 self-scoped policies are tracked."""
        assert len(SELF_SCOPED_CASES) == 5
