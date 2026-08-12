"""Policy coverage: project-scoped policies (28 policies).

Each test case grants a user ONLY the policy under test plus minimal
prerequisites, then verifies the action succeeds (positive) and that
a user WITHOUT the policy is denied (negative).

Denied is checked first because it never mutates resources — the
allowed check runs second and may modify or delete the target.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from orchestrator_test_sdk.factories import (
        AssignProjectRoleFactory,
        ProjectFactory,
        ProjectRoleFactory,
        UserFactory,
    )
    from syntara_api_client.api import SyntaraApiRegistry


if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)

from orchestrator_test_sdk.e2e.auth import api_for

from .conftest import PROJECT_SCOPED_CASES

pytestmark = [pytest.mark.e2e]


def _assert_denied(resp, case, project_id) -> None:
    """Assert that the response indicates the action was denied."""
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


@pytest.mark.parametrize("case", PROJECT_SCOPED_CASES, ids=lambda c: c.policy)
class TestProjectScopedPolicy:
    """Each case tests both: user WITHOUT the policy is denied, user WITH it succeeds."""

    def test_policy(
        self,
        syntara_base_url: str,
        admin_api: SyntaraApiRegistry,
        create_project: ProjectFactory,
        create_user: UserFactory,
        create_project_role: ProjectRoleFactory,
        assign_project_role_to_user: AssignProjectRoleFactory,
        case,
    ) -> None:
        project_id, _ = create_project(admin_api, "pol")

        ctx: dict[str, Any] = {}
        if case.setup:
            case.setup(admin_api, project_id, ctx)

        # --- Denied (first — non-mutating) ---
        if not case.skip_denied:
            user_id_d, username_d, password_d = create_user(admin_api, "pol-d")
            if case.prereqs:
                role_name_d = create_project_role(admin_api, project_id, "nopol", case.prereqs)
                assign_project_role_to_user(admin_api, project_id, user_id_d, role_name_d)

            user_api_d = api_for(syntara_base_url, username_d, password_d)
            resp_d = case.action(user_api_d, project_id, ctx)
            _assert_denied(resp_d, case, project_id)

        # --- Allowed ---
        user_id_a, username_a, password_a = create_user(admin_api, "pol-a")
        all_policies = [case.policy, *case.prereqs]
        role_name = create_project_role(admin_api, project_id, "pol", all_policies)
        assign_project_role_to_user(admin_api, project_id, user_id_a, role_name)

        user_api = api_for(syntara_base_url, username_a, password_a)
        resp = case.action(user_api, project_id, ctx)
        assert resp.is_success
